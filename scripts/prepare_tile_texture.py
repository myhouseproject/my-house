#!/usr/bin/env python3
"""Build a deterministic 4x4 bathroom-tile atlas from manufacturer product assets.

A variant may declare either a direct texture ZIP or a manufacturer/product page.
For product pages the script discovers linked ZIPs and raster images, filters them
to tile-like 2:1 faces, and records the exact source URLs used by the render.
Downloaded assets stay in build/ and are never committed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import http.client
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
import urllib.request
import zipfile

from PIL import Image, ImageOps
import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / 'modules/06_interior/extracts/bathroom-render.yaml'
USER_AGENT = 'dom-interior-render/1.0 (+https://github.com/rutkala/dom)'
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def request_bytes(url: str, *, timeout=90) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': '*/*'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def download(url: str) -> bytes:
    """Download large manufacturer archives using small bounded Range requests."""
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
        for attempt in range(10):
            request_start = segment_start + len(segment)
            headers = {
                'User-Agent': USER_AGENT,
                'Accept': '*/*',
                'Range': f'bytes={request_start}-{end}',
            }
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
                    content_range = response.headers.get('Content-Range')
                    if content_range and '/' in content_range:
                        total = int(content_range.rsplit('/', 1)[1])
                    elif getattr(response, 'status', 200) == 200:
                        full = bytearray()
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            full.extend(chunk)
                        declared = response.headers.get('Content-Length')
                        if declared and len(full) != int(declared):
                            raise OSError(f'Incomplete non-range response: {len(full)} of {declared}')
                        return bytes(full)
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
            time.sleep(min(0.25 * (attempt + 1), 2))
        if len(segment) < expected:
            raise OSError(
                f'Incomplete texture range {segment_start}-{end}: {len(segment)} of {expected} bytes'
            ) from last_error
        data.extend(segment[:expected])
        start += expected
    return bytes(data[:total])


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
            elif suffix in IMAGE_SUFFIXES:
                images.append((name, data))
    return images


def score_name(name: str, keywords):
    lowered = name.lower()
    return sum(1 for keyword in keywords if str(keyword).lower() in lowered)


def page_asset_urls(page_url: str, page_text: str):
    """Collect static asset URLs from href/src/content/srcset and JSON-ish HTML."""
    text = html.unescape(page_text).replace(r'\/', '/')
    found = set()

    quoted = re.findall(r'''(?i)(?:href|src|data-src|data-original|content)\s*=\s*["']([^"'<>]+)["']''', text)
    for value in quoted:
        found.add(urljoin(page_url, value.strip()))

    for srcset in re.findall(r'''(?i)srcset\s*=\s*["']([^"']+)["']''', text):
        for entry in srcset.split(','):
            value = entry.strip().split()[0] if entry.strip() else ''
            if value:
                found.add(urljoin(page_url, value))

    for value in re.findall(r'''https?://[^\s"'<>\\]+''', text):
        found.add(value.rstrip('),;'))

    result = []
    for url in found:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            continue
        suffix = Path(parsed.path).suffix.lower()
        if suffix in IMAGE_SUFFIXES or suffix == '.zip':
            result.append(url)
    return sorted(set(result))


def normalized_tile_image(payload: bytes, cell_px):
    with Image.open(io.BytesIO(payload)) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    if image.height > image.width:
        image = image.transpose(Image.Transpose.ROTATE_90)
    return ImageOps.fit(image, tuple(cell_px), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def select_images(items, keywords, exclude_keywords=()):
    if exclude_keywords:
        items = [(name, data) for name, data in items
                 if not any(str(keyword).lower() in name.lower() for keyword in exclude_keywords)]
    if not items:
        raise ValueError('Texture source contains no supported raster images after filtering')
    scored = [(score_name(name, keywords), name, data) for name, data in items]
    best = max(score for score, _, _ in scored)
    preferred = [(name, data) for score, name, data in scored if score == best and score > 0]
    candidates = preferred or [(name, data) for _, name, data in scored]

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


def images_from_page(page_url: str, keywords):
    page_bytes = request_bytes(page_url)
    page_text = page_bytes.decode('utf-8', errors='ignore')
    assets = page_asset_urls(page_url, page_text)
    ranked = sorted(assets, key=lambda url: (score_name(url, keywords), url), reverse=True)

    # Prefer a linked manufacturer texture ZIP when a page exposes one.
    for url in [u for u in ranked if Path(urlparse(u).path).suffix.lower() == '.zip'][:8]:
        try:
            payload = download(url)
            if zipfile.is_zipfile(io.BytesIO(payload)):
                images = archive_images(payload)
                if images:
                    return images, {
                        'source_kind': 'page-linked-zip',
                        'source_url': url,
                        'source_sha256': hashlib.sha256(payload).hexdigest(),
                        'page_url': page_url,
                    }
        except Exception:
            continue

    images = []
    for url in [u for u in ranked if Path(urlparse(u).path).suffix.lower() in IMAGE_SUFFIXES][:60]:
        try:
            payload = request_bytes(url, timeout=60)
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
            if min(width, height) < 300:
                continue
            images.append((url, payload))
        except Exception:
            continue
    if not images:
        raise ValueError(f'No usable tile images discovered on {page_url}')
    return images, {
        'source_kind': 'product-page-images',
        'source_url': page_url,
        'source_sha256': hashlib.sha256(page_bytes).hexdigest(),
        'page_url': page_url,
    }


def source_images(spec):
    keywords = spec.get('texture_member_keywords', [])
    if spec.get('texture_zip_url'):
        url = spec['texture_zip_url']
        payload = download(url)
        if not zipfile.is_zipfile(io.BytesIO(payload)):
            raise ValueError('Manufacturer texture URL did not return a ZIP archive')
        return archive_images(payload), {
            'source_kind': 'texture-zip',
            'source_url': url,
            'source_sha256': hashlib.sha256(payload).hexdigest(),
        }
    if spec.get('texture_page_url'):
        return images_from_page(spec['texture_page_url'], keywords)
    raise ValueError('Tile variant must declare texture_zip_url or texture_page_url')


def prepare(config_path: Path, variant: str):
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    variants = config.get('tile_variants', {})
    if variant not in variants:
        raise ValueError(f'Unknown tile variant: {variant}')
    spec = variants[variant]
    atlas = config['tile_texture_atlas']
    source, provenance = source_images(spec)
    candidates = select_images(
        source,
        spec.get('texture_member_keywords', []),
        spec.get('texture_exclude_keywords', []),
    )
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
        'manufacturer': spec['manufacturer'],
        'product': spec['product'],
        'product_url': spec['product_url'],
        **provenance,
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
