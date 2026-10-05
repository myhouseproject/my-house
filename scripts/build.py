#!/usr/bin/env python3
"""One source-to-release build. Default interior scope requires no network or geodesy."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid

try:
    from .build_reports import sha256, write_json, write_reports
    from .package_site import package_site, referenced_interior_textures
except ImportError:
    from build_reports import sha256, write_json, write_reports
    from package_site import package_site, referenced_interior_textures

ROOT = Path(__file__).resolve().parents[1]
GENERATED_FILES = {
    'scena_modelu.json', 'scena_lokalna.json', 'lista_elementow.json',
    'kontrola_modelu.json', 'google_model_georef.json', 'build-manifest.json',
    'sumy_sha256.txt', 'index.html', 'podglad_3d.html', 'walidacja_projektu.json',
    'decyzje_projektowe.json', 'polityki_pomieszczen.json',
}
GENERATED_SUFFIXES = {'.glb', '.kmz', '.obj', '.mtl', '.step'}
IGNORED_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', 'build',
                'dist', 'google_models', '.pytest_cache', 'archive', 'renders'}
STAGED_SUFFIXES = {'.py', '.yaml', '.yml', '.json', '.html', '.js', '.cjs',
                   '.txt', '.jpg', '.jpeg', '.png', '.tif', '.md', '.pdf'}
OUTPUT_FILES = GENERATED_FILES | {
    'dom_wnetrze.glb', 'dom_wnetrze_bloki.glb', 'dom_powloka.glb', 'dom_bryla.glb',
    'dom_model.obj', 'dom_materialy.mtl', 'dom_Gruszowa60.glb', 'dom_Gruszowa60.kmz',
}
DEPENDENCIES = ['numpy', 'scipy', 'shapely', 'trimesh', 'pyproj', 'pycollada',
                'mapbox-earcut', 'Pillow', 'networkx', 'PyYAML', 'certifi',
                'python-dateutil', 'six']
FULL_ONLY_TESTS = {'test_google_export.py', 'test_entry_levels.py'}


def source_files(root):
    """Input inventory includes source evidence hashes, never old generated outputs."""
    root = Path(root)
    for base, directories, filenames in os.walk(root):
        directories[:] = sorted(d for d in directories if d not in IGNORED_DIRS
                                and not d.startswith('.stage-'))
        for filename in sorted(filenames):
            path = Path(base) / filename
            relative = path.relative_to(root)
            if path.is_symlink() or filename in GENERATED_FILES or path.suffix in GENERATED_SUFFIXES:
                continue
            if filename in {'.git', '.build.lock'} or filename.endswith('.pyc'):
                continue
            yield relative


def source_manifest(root):
    files = {str(path): sha256(root / path) for path in source_files(root)}
    configs = {path: digest for path, digest in files.items()
               if path == 'project.yaml' or (path.startswith('modules/') and path.endswith('.yaml'))}
    digest = lambda values: hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                         stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit, dirty = None, None
    return {'git_commit': commit, 'git_worktree_dirty': dirty,
            'source_sha256': digest(files), 'config_sha256': digest(configs), 'inputs': files}


def stage_sources(root, stage, inventory):
    for name in inventory:
        relative = Path(name)
        if relative.suffix not in STAGED_SUFFIXES:
            continue
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
        if sha256(target) != inventory[name]:
            raise RuntimeError(f'Source changed while staging: {name}')
    # Cached survey/orthophoto inputs stay in data/ in source control. The old
    # exporters consume a derived working copy in the isolated staging root.
    for name in ['geoportal_teren.json', 'geoportal_ortho.jpg']:
        cache = stage / 'data' / name
        if cache.is_file():
            shutil.copyfile(cache, stage / name)


def run(stage, *command):
    print('Build:', ' '.join(str(value) for value in command), flush=True)
    subprocess.run(command, cwd=stage, check=True)


def run_tests(stage, scope):
    modules = ['tests.' + path.stem for path in sorted((stage / 'tests').glob('test_*.py'))
               if scope == 'full' or path.name not in FULL_ONLY_TESTS]
    # Discovery permits tests/ without __init__.py and avoids ambient packages named tests.
    for name in modules:
        run(stage, sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
            '-p', name.split('.')[-1] + '.py', '-v')
    run(stage, sys.executable, '-m', 'unittest', 'test_scene_downloads', '-v')
    if scope == 'full':
        run(stage, sys.executable, '-m', 'unittest', 'test_context_environment', '-v')
    node_tests = [path.relative_to(stage).as_posix() for path in sorted((stage / 'tests').glob('*.test.cjs'))]
    if not node_tests:
        raise ValueError('No Node regression tests found.')
    run(stage, 'node', '--test', *node_tests)
    return {'status': 'passed', 'scope': scope, 'python_modules': modules,
            'full_environment_test': scope == 'full', 'node_tests': node_tests}


@contextmanager
def build_lock(path):
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f'Build already running. If it was interrupted, remove {path}.') from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


def select_release(link, target):
    """Replace one pointer atomically; a failed build never replaces a prior release."""
    if link.exists() and not link.is_symlink():
        raise ValueError(f'{link} must be absent or a build-owned symlink; move this existing directory first.')
    temporary = link.with_name(link.name + '.next-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        os.replace(temporary, link)
    finally:
        temporary.unlink(missing_ok=True)


def build(root=ROOT, scope='interior', test=False, tile_format=None):
    root = Path(root).resolve()
    build_dir = root / 'build'
    build_dir.mkdir(exist_ok=True)
    with build_lock(build_dir / '.build.lock'):
        inventory = source_manifest(root)
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=build_dir) as temporary:
            stage = Path(temporary)
            stage_sources(root, stage, inventory['inputs'])
            if tile_format:
                finishes_yaml = stage / 'modules/06_interior/extracts/bathroom-finishes.yaml'
                if finishes_yaml.exists():
                    import yaml
                    data = yaml.safe_load(finishes_yaml.read_text(encoding='utf-8'))
                    data.setdefault('tile_layout', {})['active_format'] = tile_format
                    finishes_yaml.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
            run(stage, sys.executable, 'scripts/project.py', 'validate',
                '--output', 'walidacja_projektu.json')
            run(stage, sys.executable, 'scripts/sync_legacy_config.py')
            run(stage, sys.executable, 'generuj_geometrie.py', '--scope', scope, '--no-preview')
            if scope == 'full':
                run(stage, sys.executable, 'buduj_ogrod.py')
                run(stage, sys.executable, 'uaktualnij_teren_i_otoczenie.py')
                run(stage, sys.executable, 'prepare_geodesy.py')
                run(stage, sys.executable, 'eksportuj_google_earth.py')
            run(stage, sys.executable, 'export_scene_downloads.py',
                *(['--local-only'] if scope == 'interior' else []))
            run(stage, sys.executable, 'aktualizuj_podglad.py')
            report = write_reports(stage, scope)
            tests = run_tests(stage, scope) if test else {'status': 'not_requested'}
            # Reject edits made during generation, so every digest describes actual inputs.
            if inventory['source_sha256'] != source_manifest(root)['source_sha256']:
                raise RuntimeError('Source changed during build; run again to produce a consistent release.')
            release = build_dir / 'releases' / (inventory['source_sha256'][:16] + '-' + uuid.uuid4().hex[:8])
            release.mkdir(parents=True)
            try:
                for name in OUTPUT_FILES - {'build-manifest.json', 'sumy_sha256.txt'}:
                    if (stage / name).is_file():
                        shutil.copyfile(stage / name, release / name)
                if (stage / 'google_models').is_dir():
                    shutil.copytree(stage / 'google_models', release / 'google_models')
                for name in referenced_interior_textures(stage):
                    target = release / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(stage / name, target)
                output_hashes = {path.relative_to(release).as_posix(): sha256(path)
                                 for path in sorted(release.rglob('*')) if path.is_file()}
                def package_version(name):
                    try:
                        return metadata.version(name)
                    except metadata.PackageNotFoundError:
                        return 'not-installed'

                installed = {name: package_version(name) for name in DEPENDENCIES}
                project_validation = json.loads((stage / 'walidacja_projektu.json').read_text(encoding='utf-8'))
                manifest = {'schema_version': 1, 'scope': scope, **inventory,
                            'python': platform.python_version(), 'dependencies': installed,
                            'mesh_validation_status': report['status'], 'tests': tests,
                            'project_validation': {
                                'ok': project_validation['ok'],
                                'ready_for_fabrication': project_validation['ready_for_fabrication'],
                                'pending_count': len(project_validation['warnings']),
                            },
                            'outputs': output_hashes,
                            'step_status': 'archival_not_regenerated',
                            'reproducibility': 'Output hashes bind this release to the exact inputs and installed dependencies.'}
                write_json(release / 'build-manifest.json', manifest)
                checksum_files = {**output_hashes, 'build-manifest.json': sha256(release / 'build-manifest.json')}
                (release / 'sumy_sha256.txt').write_text(''.join(f'{value}  {name}\n'
                    for name, value in sorted(checksum_files.items())), encoding='utf-8')
                package_site(release, release / 'site')
                # dist always routes through the same atomic release selector.
                select_release(root / 'dist', build_dir / 'current' / 'site')
                select_release(build_dir / 'current', release)
            except Exception:
                shutil.rmtree(release)
                raise
    print(f'Gotowe: {root / "build/current/index.html"}; publikacja: {root / "dist"}', flush=True)
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['interior', 'full'], default='interior')
    parser.add_argument('--test', action='store_true', help='Run the applicable Python and Node checks before selecting the release.')
    parser.add_argument('--tile-format', '--format', choices=['120x60', '120x120', '120x280'], default=None,
                        help='Override active tile format for bathroom geometry generation.')
    args = parser.parse_args()
    build(scope=args.scope, test=args.test, tile_format=args.tile_format)


if __name__ == '__main__':
    main()
