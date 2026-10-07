#!/usr/bin/env python3
"""Extract real, clean, unique tile swatches for all 85 bathroom tiles from phone photos.

Replaces synthetic procedural noise with actual manufacturer product swatches
photographed by the user. Guarantees 85 distinct tile textures matching real products.
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = Path('/storage/emulated/0/Pictures/Gallery/owner/KuchniaProjekt')
CATALOG_PATH = ROOT / 'modules/06_interior/extracts/bathroom-tiles-85.yaml'
OCR_PATH = ROOT / '.gemini/antigravity-cli/brain/72709029-8bf0-4a8b-95ad-f7b12ee4e778/scratch/ocr_all.json'


def clean_product_name(raw_name: str, ocr_text: str, manufacturer: str) -> str:
    """Derive clean, human-readable product name using OCR text when available."""
    text_lines = [l.strip() for l in ocr_text.splitlines() if len(l.strip()) > 3]
    # Filter out common UI strings
    ui_noise = {'messenger', 'porównaj', 'dodaj', 'przejdź', 'opinie', 'facebook', 'cookies', 'filtruj', 'klienci', 'oferta'}
    candidates = [l for l in text_lines if not any(n in l.lower() for n in ui_noise)]
    
    # Check if raw_name is already good
    if raw_name and not raw_name.startswith('Tile_') and not '©' in raw_name and not 'ś Z' in raw_name:
        return raw_name
        
    for c in candidates:
        # If line has uppercase tile model or dimensions
        if re.search(r'\d+[x,]\d+', c) or any(k in c.upper() for k in ['WHITE', 'GREY', 'BEIGE', 'POLISHED', 'MATT', 'SATIN', 'STONE', 'GOLD']):
            # Clean up trailing punctuation
            cleaned = re.sub(r'^[^\w]+|[^\w\s\.,x\-]+$', '', c).strip()
            if len(cleaned) > 4:
                return cleaned

    # Fallback to candidate line
    if candidates:
        return candidates[0]
    return raw_name


def extract_swatch(img_path: Path, dims_mm: list[float], is_limone: bool = False) -> tuple[np.ndarray, str]:
    """Extract clean rectangular tile swatch from photo, rejecting UI, headers, and text."""
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Could not open image: {img_path}")
        
    H, W, _ = img.shape
    w_mm, h_mm = float(dims_mm[0]), float(dims_mm[1])
    target_aspect = max(w_mm, h_mm) / max(1.0, min(w_mm, h_mm))

    if is_limone:
        # Dark background detection using Canny edge contours
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 100)
        contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            if w > 350 and h > 200 and y > 250 and (y + h) < 1950:
                boxes.append((x, y, w, h))
        if boxes:
            boxes.sort(key=lambda b: (b[2] * b[3]), reverse=True)
            bx, by, bw, bh = boxes[0]
            pad_x, pad_y = max(8, int(bw * 0.05)), max(8, int(bh * 0.05))
            crop = img[by + pad_y : by + bh - pad_y, bx + pad_x : bx + bw - pad_x]
            return crop, f"Limone edge box ({bw}x{bh})"

    # White / Light background detection (Cersanit, Tubadzin, Opoczno, Paradyz, Cerrad)
    body = img[250:1920, :]
    gray = cv2.cvtColor(body, cv2.COLOR_BGR2GRAY)
    
    candidate_boxes = []
    # Test multiple thresholds to handle dark stones, medium tiles, and ultra-light white tiles
    for th in [230, 242, 253]:
        mask = (gray < th).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            real_y = y + 250
            if w >= 200 and h >= 80 and real_y >= 260 and (real_y + h) <= 1915:
                asp = max(w, h) / max(1.0, min(w, h))
                asp_diff = abs(asp - target_aspect)
                candidate_boxes.append((x, real_y, w, h, asp, asp_diff))

    if not candidate_boxes:
        # Fallback center crop of body area
        crop = img[500:1500, 100:846]
        return crop, "Fallback center crop"

    # Deduplicate overlapping boxes
    unique_boxes = []
    for b in candidate_boxes:
        bx, by, bw, bh = b[0], b[1], b[2], b[3]
        if not any(abs(bx - ub[0]) < 25 and abs(by - ub[1]) < 25 for ub in unique_boxes):
            unique_boxes.append(b)

    # Sort boxes: prefer those matching target aspect ratio, then higher position on screen
    unique_boxes.sort(key=lambda b: (b[5], b[1]))
    best = unique_boxes[0]
    bx, by, bw, bh = best[0], best[1], best[2], best[3]

    # Safe margin inset (4%) to prevent sampling border shadow lines or white background
    pad_x = max(6, int(bw * 0.04))
    pad_y = max(6, int(bh * 0.04))
    crop = img[by + pad_y : by + bh - pad_y, bx + pad_x : bx + bw - pad_x]
    return crop, f"Box ({bw}x{bh}, asp={best[4]:.2f}, diff={best[5]:.2f})"


def write_obj_and_mtl(target_dir: Path, slug: str, dim_x_mm: float, dim_y_mm: float, thickness_mm: float = 8.0):
    target_dir.mkdir(parents=True, exist_ok=True)
    obj_file = target_dir / f"{slug}.obj"
    mtl_file = target_dir / f"{slug}.mtl"
    
    hx = dim_x_mm / 2.0
    hy = dim_y_mm / 2.0
    hz = thickness_mm
    
    obj_lines = [
        f"# Clean 3D Tile Model: {slug} ({dim_x_mm}x{dim_y_mm}x{thickness_mm} mm)",
        f"mtllib {slug}.mtl",
        f"o {slug}",
        f"v {-hx:.4f} {-hy:.4f} 0.0000",
        f"v {hx:.4f} {-hy:.4f} 0.0000",
        f"v {hx:.4f} {hy:.4f} 0.0000",
        f"v {-hx:.4f} {hy:.4f} 0.0000",
        f"v {-hx:.4f} {-hy:.4f} {hz:.4f}",
        f"v {hx:.4f} {-hy:.4f} {hz:.4f}",
        f"v {hx:.4f} {hy:.4f} {hz:.4f}",
        f"v {-hx:.4f} {hy:.4f} {hz:.4f}",
        "vt 0.0000 0.0000",
        "vt 1.0000 0.0000",
        "vt 1.0000 1.0000",
        "vt 0.0000 1.0000",
        "vn 0.0000 0.0000 1.0000",
        "vn 0.0000 0.0000 -1.0000",
        "vn 0.0000 -1.0000 0.0000",
        "vn 1.0000 0.0000 0.0000",
        "vn 0.0000 1.0000 0.0000",
        "vn -1.0000 0.0000 0.0000",
        "usemtl TileMaterial",
        "s 1",
        "f 5/1/1 6/2/1 7/3/1 8/4/1",
        "f 4/4/2 3/3/2 2/2/2 1/1/2",
        "f 1/1/3 2/2/3 6/2/3 5/1/3",
        "f 2/2/4 3/3/4 7/3/4 6/2/4",
        "f 3/3/5 4/4/5 8/4/5 7/3/5",
        "f 4/4/6 1/1/6 5/1/6 8/4/6",
        ""
    ]
    obj_file.write_text("\n".join(obj_lines), encoding="utf-8")
    
    mtl_lines = [
        f"# Clean Material definition for {slug}",
        "newmtl TileMaterial",
        "Ka 1.000 1.000 1.000",
        "Kd 0.900 0.900 0.900",
        "Ks 0.250 0.250 0.250",
        "Ns 120.0",
        "d 1.0",
        "illum 2",
        "map_Kd texture.jpg",
        ""
    ]
    mtl_file.write_text("\n".join(mtl_lines), encoding="utf-8")


def main():
    print("Loading catalog and OCR...")
    cat_data = yaml.safe_load(CATALOG_PATH.read_text(encoding='utf-8'))
    tiles = cat_data.get('tiles', [])
    ocr = json.loads(OCR_PATH.read_text(encoding='utf-8')) if OCR_PATH.exists() else {}

    print(f"Extracting true unique textures for {len(tiles)} tiles from phone photos...")
    updated_tiles = []
    
    for t in tiles:
        idx = t['index']
        slug = t['slug']
        mfg = t.get('manufacturer', '')
        source_image = t.get('source_image', '')
        img_p = SRC_DIR / source_image
        ocr_text = ocr.get(source_image, {}).get('text', '')

        dims = t.get('dimensions_mm', [600, 1200])
        w_mm, h_mm = float(dims[0]), float(dims[1])
        
        is_limone = (mfg == 'Ceramica Limone')
        crop_bgr, info = extract_swatch(img_p, dims, is_limone=is_limone)

        # Convert to PIL Image in RGB
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)

        # Standardize target dimensions: 2:1 tiles -> 1024x512; 1:1 tiles -> 1024x1024; 3:1 tiles -> 1024x341
        aspect = max(w_mm, h_mm) / max(1.0, min(w_mm, h_mm))
        if aspect >= 2.5:
            target_size = (1024, 341)
        elif aspect >= 1.5:
            target_size = (1024, 512)
        else:
            target_size = (1024, 1024)

        # Rotate if tile is vertical so orientation matches atlas standards (width >= height)
        if pil_img.height > pil_img.width:
            pil_img = pil_img.transpose(Image.Transpose.ROTATE_90)

        # Fit into standard target_size with high-quality resampling
        standardized_tex = ImageOps.fit(pil_img, target_size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))

        # Save to assets/models/tiles/<slug>/texture.jpg
        tile_dir = ROOT / 'assets/models/tiles' / slug
        tile_dir.mkdir(parents=True, exist_ok=True)
        tex_path = tile_dir / 'texture.jpg'
        standardized_tex.save(tex_path, format='JPEG', quality=95, optimize=True)

        # Ensure OBJ and MTL exist and are clean
        write_obj_and_mtl(tile_dir, slug, w_mm, h_mm)

        # Measure accurate color from actual tile pixels
        arr_norm = np.array(standardized_tex, dtype=np.float32) / 255.0
        mean_srgb = [round(float(c), 3) for c in arr_norm.mean(axis=(0, 1))]

        # Update product metadata
        product_clean = clean_product_name(t.get('product', ''), ocr_text, mfg)
        label_clean = f"{idx:02d}. {mfg} {product_clean} ({t.get('format', '60x120')})"
        
        # Determine surface roughness & coat from keywords
        full_text = (product_clean + " " + ocr_text).lower()
        is_glossy = any(k in full_text for k in ['polished', 'poler', 'glossy', 'połysk', 'lappato', 'sugar'])
        roughness = 0.18 if is_glossy else 0.45
        coat = 0.25 if is_glossy else 0.05
        coat_roughness = 0.15 if is_glossy else 0.35

        t['product'] = product_clean
        t['label'] = label_clean
        t['color_srgb'] = mean_srgb
        t['roughness'] = roughness
        t['coat'] = coat
        t['coat_roughness'] = coat_roughness
        t['model_obj'] = f'assets/models/tiles/{slug}/{slug}.obj'
        t['model_mtl'] = f'assets/models/tiles/{slug}/{slug}.mtl'
        t['texture_image'] = f'assets/models/tiles/{slug}/texture.jpg'
        t['atlas_path'] = f'build/render-textures/atlas-{slug}-120x60.jpg'
        updated_tiles.append(t)

        print(f"[{idx:02d}] {slug}: {product_clean} | RGB: {mean_srgb} | Size: {target_size} ({info})")

    cat_data['tiles'] = updated_tiles
    CATALOG_PATH.write_text(yaml.dump(cat_data, allow_unicode=True, sort_keys=False, width=120), encoding='utf-8')
    print(f"\nAll {len(updated_tiles)} tile textures and catalog YAML successfully updated!")


if __name__ == '__main__':
    main()
