#!/usr/bin/env python3
"""Prepare a bounded, manual render job; never interpret camera input as code."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT.parent / 'render-job'


def prepare(camera_text, quality):
    if quality not in ('preview', 'final'):
        raise ValueError('Unknown render quality')
    if len(camera_text.encode('utf-8')) > 65536:
        raise ValueError('Camera JSON is too large')
    camera = json.loads(camera_text) if camera_text.strip() else None
    if camera is not None:
        if not isinstance(camera, dict):
            raise ValueError('Camera must be a JSON object')
        settings = yaml.safe_load((ROOT / 'modules/06_interior/extracts/portal-render.yaml').read_text())
        resolution = camera.get('resolution')
        if (not isinstance(resolution, list) or len(resolution) != 2 or
                any(type(n) is not int or n < 16 for n in resolution)):
            raise ValueError('Camera must declare a pixel resolution')
        maximum = int(settings['preview_long_edge_px'] if quality == 'preview' else settings['max_long_edge_px'])
        scale = min(1, maximum / max(resolution))
        camera['resolution'] = [max(16, round(n * scale)) for n in resolution]
        camera['aspect_ratio'] = camera['resolution'][0] / camera['resolution'][1]
    JOB.mkdir(exist_ok=True)
    arguments = ['--scene', str(ROOT / 'build/current/scena_lokalna.json'),
                 '--quality', quality, '--output', str(JOB / 'output')]
    if camera is not None:
        path = JOB / 'camera.json'
        path.write_text(json.dumps(camera, ensure_ascii=False), encoding='utf-8')
        arguments += ['--scope', 'house', '--camera-file', str(path)]
    else:
        arguments += ['--scope', 'bathroom', '--camera', 'entrance']
    command = [sys.executable, str(ROOT / 'scripts/render_bathroom.py'), *arguments, '--validate-only']
    subprocess.run(command, cwd=ROOT, check=True)
    (JOB / 'arguments.json').write_text(json.dumps(arguments), encoding='utf-8')
    return arguments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        arguments = json.loads((JOB / 'arguments.json').read_text(encoding='utf-8'))
        subprocess.run([sys.executable, str(ROOT / 'scripts/render_bathroom.py'), *arguments],
                       cwd=ROOT, check=True)
    else:
        prepare(os.environ.get('PORTAL_CAMERA_JSON', ''), os.environ.get('PORTAL_RENDER_QUALITY', 'final'))


if __name__ == '__main__':
    main()
