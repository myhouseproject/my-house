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

import copy
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'modules/06_interior/extracts/bathroom-render.yaml'


def download(url: str) -> bytes:
    """Download large manufacturer archives using small bounded Range requests.

    The texture host truncates long responses on CI runners. Four-megabyte
    ranges keep every HTTP response short and make retries deterministic.
    """
    cache_dir = ROOT / 'build/render-textures/cache'
    cache_file = cache_dir / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}.zip"
    if cache_file.exists() and cache_file.stat().st_size > 1024:
        return cache_file.read_bytes()

    segment_size = 4 * 1024 * 1024
    data = bytearray()
    total = None
    start = 0
    while total is None or start < total:
        end = start + segment_size - 1
        if total is not None:
            end = min(end, total - 1)
        expected = end - start + 1
        segment = bytearray()
        segment_start = start
        last_error = None
        for attempt in range(15):
            request_start = segment_start + len(segment)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Range': f'bytes={request_start}-{end}',
            }
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as response:
                    content_range = response.headers.get('Content-Range')
                    if content_range and '/' in content_range:
                        total = int(content_range.rsplit('/', 1)[1])
                    elif getattr(response, 'status', 200) == 200:
                        # Range unsupported: accept a complete response only.
                        full = bytearray()
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            full.extend(chunk)
                        declared = response.headers.get('Content-Length')
                        if declared and len(full) != int(declared):
                            raise OSError(f'Incomplete non-range response: {len(full)} of {declared}')
                        payload = bytes(full)
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_bytes(payload)
                        return payload
                    while len(segment) < expected:
                        chunk = response.read(min(1024 * 1024, expected - len(segment)))
                        if not chunk:
                            break
                        segment.extend(chunk)
            except http.client.IncompleteRead as exc:
                if exc.partial:
                    segment.extend(exc.partial)
                last_error = exc
            except Exception as exc:
                last_error = exc
            if len(segment) >= expected:
                break
            time.sleep(min(0.5 * (attempt + 1), 5))
        if len(segment) < expected:
            raise OSError(
                f'Incomplete texture range {segment_start}-{end}: {len(segment)} of {expected} bytes'
            ) from last_error
        data.extend(segment[:expected])
        start += expected
    payload = bytes(data[:total])
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_bytes(payload)
    return payload


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
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(payload)) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    target_w, target_h = cell_px
    if target_w >= target_h and image.height > image.width:
        image = image.transpose(Image.Transpose.ROTATE_90)
    elif target_w < target_h and image.width > image.height:
        image = image.transpose(Image.Transpose.ROTATE_90)
    # Fit avoids leaking borders/labels into the rendered material.
    return ImageOps.fit(image, tuple(cell_px), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def select_images(items, keywords):
    if not items:
        raise ValueError('Texture archive contains no supported raster images')
    from PIL import Image
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
    from PIL import Image
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


def atlas_relative_path(variant: str, tile_format: str = '120x60') -> Path:
    return Path(f'build/render-textures/atlas-{variant}-{tile_format}.jpg')


def prepare(config_path: Path, variant: str, tile_format: str = '120x60'):
    import shutil
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    variants = config.get('tile_variants', {})
    if variant not in variants:
        raise ValueError(f'Unknown tile variant: {variant}')
    spec = variants[variant]
    atlas = copy.deepcopy(config['tile_texture_atlas'])
    presets = config.get('tile_format_presets', {})
    if tile_format in presets:
        atlas.update(presets[tile_format])
    if tile_format != '120x60':
        atlas_path = Path(atlas['path'])
        atlas['path'] = str(atlas_path.with_stem(f"{atlas_path.stem}-{tile_format}"))
    output = ROOT / atlas_relative_path(variant, tile_format)
    default_out = ROOT / atlas['path']
    asset_fallback = ROOT / 'assets/textures/tiles' / output.name
    if asset_fallback.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset_fallback, output)
        json_fallback = asset_fallback.with_suffix('.json')
        if json_fallback.exists():
            shutil.copy2(json_fallback, output.with_suffix('.json'))
        if output != default_out:
            shutil.copy2(output, default_out)
            if json_fallback.exists():
                shutil.copy2(json_fallback, default_out.with_suffix('.json'))
        if json_fallback.exists():
            return json.loads(json_fallback.read_text(encoding='utf-8'))
    payload = download(spec['texture_zip_url'])
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError('Manufacturer texture URL did not return a ZIP archive')
    candidates = select_images(archive_images(payload), spec.get('texture_member_keywords', []))
    used = build_atlas(
        candidates,
        output,
        int(atlas['columns']),
        int(atlas['rows']),
        [int(value) for value in atlas['cell_px']],
    )
    default_out = ROOT / atlas['path']
    if output != default_out:
        shutil.copy2(output, default_out)
    manifest = {
        'schema_version': 1,
        'variant': variant,
        'tile_format': tile_format,
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
    if output != default_out:
        default_out.with_suffix('.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--variant', help='Tile variant name to prepare')
    parser.add_argument('--tile-format', '--format', default='120x60',
                        choices=['120x60', '120x120', '120x280'])
    parser.add_argument('--all', action='store_true',
                        help='Prepare textures for all matrix variants and formats')
    args = parser.parse_args(argv)

    if args.all:
        tasks = [
            ('opoczno_calacatta_marble', '120x60'),
            ('opoczno_calacatta_marble', '120x120'),
            ('opoczno_calacatta_marble', '120x280'),
            ('opoczno_calacatta_paonazzo', '120x60'),
            ('opoczno_calacatta_monet', '120x60'),
            ('opoczno_calacatta_gold', '120x60'),
            ('tubadzin_marmo_d_oro', '120x60'),
            ('paradyz_horizon_gold', '120x60'),
            ('cerrad_calacatta_gold', '120x60'),
        ]
        results = {}
        for variant, fmt in tasks:
            print(f'==> Preparing tile texture atlas: {variant} ({fmt})', flush=True)
            results[f'{variant}_{fmt}'] = prepare(args.config, variant, fmt)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    if not args.variant:
        parser.error('--variant is required unless --all is specified')
    print(json.dumps(prepare(args.config, args.variant, args.tile_format), ensure_ascii=False))


if __name__ == '__main__':
    main()
