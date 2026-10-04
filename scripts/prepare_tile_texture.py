#!/usr/bin/env python3
"""Build a deterministic 4x4 bathroom-tile atlas from a declared manufacturer texture pack.

The raw texture archive is downloaded only for rendering and is not committed.
The resulting atlas remains inside build/ so Blender can consume it as a
project-local image texture.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
from pathlib import Path
import re
import time
import urllib.request
import zipfile

from PIL import Image, ImageOps
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'modules/06_interior/extracts/bathroom-render.yaml'


def download(url: str) -> bytes:
    """Download large texture packs with resumable Range requests.

    The Opoczno asset host occasionally closes long transfers early. Reading in
    chunks and resuming from the last byte avoids treating a partial 30–40 MB
    response as a complete ZIP.
    """
    data = bytearray()
    total = None
    last_error = None
    for attempt in range(12):
        start = len(data)
        headers = {
            'User-Agent': 'dom-interior-render/1.0 (+https://github.com/rutkala/dom)',
            'Accept': '*/*',
        }
        if start:
            headers['Range'] = f'bytes={start}-'
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = getattr(response, 'status', 200)
                content_range = response.headers.get('Content-Range')
                if start and status == 200 and not content_range:
                    # Server ignored Range; restart rather than concatenate duplicates.
                    data.clear()
                    start = 0
                if content_range and '/' in content_range:
                    total = int(content_range.rsplit('/', 1)[1])
                elif response.headers.get('Content-Length'):
                    length = int(response.headers['Content-Length'])
                    total = start + length if status == 206 else length
                while True:
                    try:
                        chunk = response.read(1024 * 1024)
                    except http.client.IncompleteRead as exc:
                        if exc.partial:
                            data.extend(exc.partial)
                        raise
                    if not chunk:
                        break
                    data.extend(chunk)
        except Exception as exc:
            last_error = exc
        if total is not None and len(data) >= total:
            return bytes(data[:total])
        if total is None and data and last_error is None:
            return bytes(data)
        time.sleep(min(1 + attempt, 8))
    raise OSError(
        f'Incomplete texture download after retries: {len(data)} of {total or "unknown"} bytes'
    ) from last_error


def archive_images(payload: bytes, prefix: str = '', depth: int = 0):
    if depth > 3:
        return []
    images = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = f'{prefix}{info.filename}'
            suffix = Path(info.filename).suffix.lower()
            data = archive.read(info)
            if suffix == '.zip':
                try:
                    images.extend(archive_images(data, prefix=name+'/', depth=depth+1))
                except zipfile.BadZipFile:
                    continue
            elif suffix in {'.jpg', '.jpeg', '.png', '.webp'}:
                images.append((name, data))
    return images


def score_name(name: str, keywords):
    lowered = name.lower()
    return sum(1 for keyword in keywords if str(keyword).lower() in lowered)


def normalized_tile_image(payload: bytes, cell_px):
    with Image.open(io.BytesIO(payload)) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    if image.height > image.width:
        image = image.transpose(Image.Transpose.ROTATE_90)
    # Manufacturer files are expected to be close to 2:1 for 60x120 tiles.
    # Fit avoids leaking borders/labels into the rendered material.
    return ImageOps.fit(image, tuple(cell_px), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def select_images(items, keywords):
    if not items:
        raise ValueError('Texture archive contains no supported raster images')
    scored = [(score_name(name, keywords), name, data) for name, data in items]
    best = max(score for score, _, _ in scored)
    preferred = [(name, data) for score, name, data in scored if score == best and score > 0]
    candidates = preferred or [(name, data) for _, name, data in scored]

    # Prefer images whose post-orientation proportions resemble a 60x120 tile.
    ratio_matches, fallback = [], []
    for name, data in candidates:
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except Exception:
            continue
        long_side, short_side = max(width, height), min(width, height)
        ratio = long_side / max(1, short_side)
        target = ratio_matches if 1.65 <= ratio <= 2.35 else fallback
        target.append((name, data))
    return ratio_matches or fallback


def evenly_spaced(items, count):
    if len(items) <= count:
        return items
    if count == 1:
        return [items[0]]
    return [items[round(i * (len(items)-1) / (count-1))] for i in range(count)]


def build_atlas(items, output: Path, columns: int, rows: int, cell_px):
    selected = evenly_spaced(sorted(items, key=lambda item: item[0]), columns * rows)
    if not selected:
        raise ValueError('No usable manufacturer texture images found')
    canvas = Image.new('RGB', (columns * cell_px[0], rows * cell_px[1]))
    used = []
    for index in range(columns * rows):
        name, payload = selected[index % len(selected)]
        tile = normalized_tile_image(payload, cell_px)
        x = (index % columns) * cell_px[0]
        y = (index // columns) * cell_px[1]
        canvas.paste(tile, (x, y))
        used.append(name)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format='JPEG', quality=95, subsampling=0, optimize=True)
    return used


def prepare(config_path: Path, variant: str):
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    variants = config.get('tile_variants', {})
    if variant not in variants:
        raise ValueError(f'Unknown tile variant: {variant}')
    spec = variants[variant]
    atlas = config['tile_texture_atlas']
    payload = download(spec['texture_zip_url'])
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError('Manufacturer texture URL did not return a ZIP archive')
    candidates = select_images(archive_images(payload), spec.get('texture_member_keywords', []))
    output = ROOT / atlas['path']
    used = build_atlas(
        candidates,
        output,
        int(atlas['columns']),
        int(atlas['rows']),
        [int(value) for value in atlas['cell_px']],
    )
    manifest = {
        'schema_version': 1,
        'variant': variant,
        'label': spec['label'],
        'product': spec['product'],
        'product_url': spec['product_url'],
        'texture_zip_url': spec['texture_zip_url'],
        'texture_zip_sha256': hashlib.sha256(payload).hexdigest(),
        'atlas_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'atlas_path': str(output.relative_to(ROOT)),
        'atlas_grid': [int(atlas['columns']), int(atlas['rows'])],
        'tile_size_mm': atlas['tile_size_mm'],
        'source_members': used,
    }
    output.with_suffix('.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--variant', required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare(args.config, args.variant), ensure_ascii=False))


if __name__ == '__main__':
    main()
