#!/usr/bin/env python3
"""Package a public portal using a strict allowlist, excluding project evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

PUBLIC_FILES = {
    'index.html', 'podglad_3d.html', 'dom_wnetrze.glb', 'dom_wnetrze_bloki.glb',
    'dom_powloka.glb', 'dom_bryla.glb', 'dom_Gruszowa60.glb', 'dom_Gruszowa60.kmz',
    'google_model_georef.json', 'kontrola_modelu.json', 'lista_elementow.json',
    'build-manifest.json', 'sumy_sha256.txt', 'walidacja_projektu.json',
}


def referenced_interior_textures(source):
    """Serve only assets explicitly used by the generated scene, never evidence."""
    references = set()
    for filename in ('scena_lokalna.json', 'scena_modelu.json'):
        scene = Path(source) / filename
        if not scene.is_file():
            continue
        for part in json.loads(scene.read_text(encoding='utf-8')).get('parts', []):
            value = part.get('texture_url')
            if not value:
                continue
            candidate = Path(value)
            if (candidate.is_absolute() or '..' in candidate.parts
                    or candidate.parts[:2] != ('assets', 'textures')
                    or candidate.suffix.lower() not in {'.png', '.jpg', '.jpeg'}):
                raise ValueError(f'Invalid interior texture path: {value}')
            references.add(candidate.as_posix())
    return references


def referenced_google_models(source):
    metadata = source / 'google_model_georef.json'
    if not metadata.is_file():
        return set()
    # Only explicit, existing current model references, never historical versions.
    references = set()
    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str) and value.startswith('google_models/'):
            candidate = Path(value)
            if candidate.suffix == '.glb' and '..' not in candidate.parts and len(candidate.parts) == 2:
                references.add(candidate.as_posix())
    visit(json.loads(metadata.read_text(encoding='utf-8')))
    return references


def package_site(source, destination):
    source, destination = Path(source), Path(destination)
    if not (source / 'index.html').is_file():
        raise ValueError('Missing generated index.html')
    destination.mkdir(parents=True, exist_ok=False)
    references = referenced_google_models(source) | referenced_interior_textures(source)
    for name in sorted(PUBLIC_FILES | references):
        path = source / name
        if path.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        elif name in references:
            raise ValueError(f'Missing referenced public asset: {name}')
    (destination / '.nojekyll').touch()
    # Website checksums refer only to files actually served from this package.
    checksums = []
    for path in sorted(destination.rglob('*')):
        if path.is_file() and path.name != 'sumy_sha256.txt':
            checksums.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(destination).as_posix()}\n')
    (destination / 'sumy_sha256.txt').write_text(''.join(checksums), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    package_site(args.source, args.destination)
