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
    for name in sorted(PUBLIC_FILES | referenced_google_models(source)):
        path = source / name
        if path.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        elif name.startswith('google_models/'):
            raise ValueError(f'Missing referenced Google model: {name}')
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
