#!/usr/bin/env python3
"""Generate pristine architectural PBR textures and 3D OBJ models for all 85 bathroom tiles.

Replaces dirty screenshot crops with clean, photorealistic tile face textures
and OBJ geometry. Zero room photos, zero screenshot UI.
"""
import os
import json
import math
import numpy as np
from PIL import Image
from pathlib import Path
import scipy.ndimage as ndimage
import yaml

ROOT = Path(__file__).resolve().parents[1]

def make_noise(h, w, scale, seed=None):
    if seed is not None:
        np.random.seed(seed)
    sh, sw = max(2, int(h / scale)), max(2, int(w / scale))
    grid = np.random.randn(sh, sw).astype(np.float32)
    zoom_y = h / sh
    zoom_x = w / sw
    smooth = ndimage.zoom(grid, (zoom_y, zoom_x), order=1)[:h, :w]
    return smooth

def fbm(h, w, octaves=4, initial_scale=64, persistence=0.5, seed=0):
    total = np.zeros((h, w), dtype=np.float32)
    scale = initial_scale
    weight = 1.0
    norm = 0.0
    for i in range(octaves):
        n = make_noise(h, w, scale, seed=seed + i * 17)
        total += weight * n
        norm += weight
        scale = max(2, scale / 2)
        weight *= persistence
    return total / norm

def generate_marble_texture(w, h, base_rgb, vein_rgb, seed=42):
    np.random.seed(seed)
    n1 = fbm(h, w, octaves=4, initial_scale=128, seed=seed)
    n2 = fbm(h, w, octaves=4, initial_scale=64, seed=seed + 101)
    
    y, x = np.mgrid[0:h, 0:w]
    warp_x = x + 40 * n1 + 20 * n2
    warp_y = y + 40 * n2 + 20 * n1
    
    phase = (warp_x * 0.007 + warp_y * 0.011)
    vein_field = np.abs(np.sin(phase * math.pi * 3) + 0.4 * np.sin(phase * math.pi * 7))
    vein_mask = np.exp(-12.0 * (vein_field ** 2))
    
    phase2 = (warp_x * 0.016 - warp_y * 0.009)
    vein2 = np.exp(-22.0 * (np.sin(phase2 * math.pi * 4) ** 2))
    vein_mask = np.clip(vein_mask + 0.35 * vein2, 0.0, 1.0)
    
    cloud = 0.03 * n1
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    vein = np.array(vein_rgb, dtype=np.float32) / 255.0
    
    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        col_base = np.clip(base[c] + cloud, 0.0, 1.0)
        img[:, :, c] = (1.0 - vein_mask) * col_base + vein_mask * vein[c]
        
    speckle = 0.008 * np.random.randn(h, w)
    img = np.clip(img + speckle[:, :, None], 0.0, 1.0)
    return (img * 255).astype(np.uint8)

def generate_travertine_texture(w, h, base_rgb, seed=42):
    np.random.seed(seed)
    y, x = np.mgrid[0:h, 0:w]
    n1 = fbm(h, w, octaves=4, initial_scale=128, seed=seed)
    n2 = fbm(h, w, octaves=4, initial_scale=32, seed=seed + 50)
    
    strat = np.sin((y + 25 * n1) * 0.035) * 0.5 + 0.5
    strat += 0.3 * np.sin((y + 10 * n2) * 0.1)
    strat = (strat - strat.min()) / (strat.max() - strat.min() + 1e-5)
    
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    dark_tone = base * 0.86
    light_tone = np.clip(base * 1.06, 0, 1)
    
    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        img[:, :, c] = (1.0 - strat) * dark_tone[c] + strat * light_tone[c]
        
    pits = np.random.rand(h, w)
    pit_mask = (pits > 0.994).astype(np.float32)
    pit_mask = ndimage.gaussian_filter(pit_mask, sigma=0.7) * 1.2
    pit_mask = np.clip(pit_mask, 0, 0.3)
    img = img * (1.0 - pit_mask[:, :, None])
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)

def generate_onyx_texture(w, h, base_rgb, vein_rgb, seed=42):
    np.random.seed(seed)
    y, x = np.mgrid[0:h, 0:w]
    n1 = fbm(h, w, octaves=5, initial_scale=160, seed=seed)
    n2 = fbm(h, w, octaves=4, initial_scale=80, seed=seed + 77)
    
    dist = np.hypot(x - w*0.4 + 50*n1, y - h*0.5 + 50*n2) * 0.018
    rings = np.sin(dist + 2.0 * n1) * 0.5 + 0.5
    
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    vein = np.array(vein_rgb, dtype=np.float32) / 255.0
    highlight = np.clip(base * 1.12, 0, 1)
    
    t1 = np.clip(rings * 1.1, 0, 1)
    t2 = np.clip((n2 + 1) * 0.5, 0, 1)
    
    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        mid = (1.0 - t1) * base[c] + t1 * vein[c]
        img[:, :, c] = (1.0 - 0.25 * t2) * mid + 0.25 * t2 * highlight[c]
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)

def generate_wood_texture(w, h, base_rgb, seed=42):
    np.random.seed(seed)
    y, x = np.mgrid[0:h, 0:w]
    n1 = fbm(h, w, octaves=4, initial_scale=128, seed=seed)
    grain = np.sin((x * 0.18 + 12 * n1)) * 0.5 + 0.5
    grain += 0.35 * np.sin(x * 0.5 + 6 * n1)
    fine = make_noise(h, w, 8, seed=seed+33)
    grain = np.clip(grain * 0.7 + fine * 0.15, 0, 1)
    
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    dark = base * 0.8
    light = np.clip(base * 1.08, 0, 1)
    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        img[:, :, c] = (1.0 - grain) * dark[c] + grain * light[c]
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)

def generate_ceramic_texture(w, h, base_rgb, is_glossy=False, seed=42):
    np.random.seed(seed)
    base = np.array(base_rgb, dtype=np.float32) / 255.0
    n = fbm(h, w, octaves=3, initial_scale=64, seed=seed) * 0.02
    speckle = np.random.randn(h, w) * (0.005 if is_glossy else 0.01)
    img = np.zeros((h, w, 3), dtype=np.float32)
    for c in range(3):
        img[:, :, c] = np.clip(base[c] + n + speckle, 0, 1)
    return (img * 255).astype(np.uint8)

def write_obj_and_mtl(target_dir, slug, dim_x_mm, dim_y_mm, thickness_mm=8.0):
    target_dir.mkdir(parents=True, exist_ok=True)
    obj_file = target_dir / f"{slug}.obj"
    mtl_file = target_dir / f"{slug}.mtl"
    
    hx = dim_x_mm / 2.0
    hy = dim_y_mm / 2.0
    hz = thickness_mm
    
    obj_lines = [
        f"# Tile 3D Model: {slug} ({dim_x_mm}x{dim_y_mm}x{thickness_mm} mm)",
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

def classify_tile(tile, ocr_text):
    text = (tile.get('product', '') + ' ' + tile.get('label', '') + ' ' + ocr_text).lower()
    
    # Dimensions
    dims = tile.get('dimensions_mm', [600, 1200])
    w_mm, h_mm = float(dims[0]), float(dims[1])
    
    # Category detection
    if any(k in text for k in ['wood', 'drewno', 'tiger wood', 'infinity wood']):
        mat = 'wood'
        base_rgb = [198, 168, 134]
        roughness = 0.55
        coat = 0.02
    elif any(k in text for k in ['onyks', 'onyx']):
        mat = 'onyx'
        if 'grey' in text or 'szar' in text:
            base_rgb = [215, 218, 222]
            vein_rgb = [150, 155, 165]
        elif 'white' in text:
            base_rgb = [242, 240, 235]
            vein_rgb = [190, 185, 175]
        else: # gold/honey
            base_rgb = [238, 224, 195]
            vein_rgb = [185, 150, 100]
        roughness = 0.12
        coat = 0.28
    elif any(k in text for k in ['calacatta', 'statuario', 'carrara', 'marmo', 'marble', 'mistari', 'arriatta']):
        mat = 'marble'
        if 'gold' in text:
            base_rgb = [245, 243, 238]
            vein_rgb = [188, 162, 115]
        elif 'warm' in text or 'cream' in text:
            base_rgb = [246, 242, 234]
            vein_rgb = [165, 158, 148]
        else:
            base_rgb = [246, 246, 244]
            vein_rgb = [145, 148, 152]
        roughness = 0.18 if ('polished' in text or 'poler' in text or 'glossy' in text) else 0.38
        coat = 0.25 if ('polished' in text or 'poler' in text or 'glossy' in text) else 0.08
    elif any(k in text for k in ['travertino', 'travertine', 'calcare', 'stone', 'tessuo', 'noble', 'gamilton', 'arcadia', 'imperiale', 'kianto', 'tambria']):
        mat = 'travertine'
        if 'grey' in text or 'light grey' in text:
            base_rgb = [218, 217, 214]
        elif 'cream' in text or 'ivory' in text or 'pearl' in text:
            base_rgb = [238, 232, 220]
        else:
            base_rgb = [228, 220, 204]
        roughness = 0.22 if ('polished' in text or 'poler' in text) else 0.42
        coat = 0.20 if ('polished' in text or 'poler' in text) else 0.06
    elif any(k in text for k in ['stucco', 'cement', 'concrete', 'essence', 'carpetstone']):
        mat = 'concrete'
        base_rgb = [220, 218, 214]
        roughness = 0.50
        coat = 0.04
    else: # Plain ceramic
        mat = 'ceramic'
        is_glossy = 'glossy' in text or 'połysk' in text or 'poler' in text
        if 'cream' in text or 'beige' in text:
            base_rgb = [240, 235, 222]
        elif 'grey' in text:
            base_rgb = [218, 218, 218]
        else:
            base_rgb = [248, 247, 245]
        roughness = 0.15 if is_glossy else 0.40
        coat = 0.30 if is_glossy else 0.06
        
    return {
        'mat': mat,
        'base_rgb': base_rgb,
        'vein_rgb': locals().get('vein_rgb', [160, 160, 160]),
        'roughness': roughness,
        'coat': coat,
        'is_glossy': 'polished' in text or 'glossy' in text or 'poler' in text,
        'w_mm': w_mm,
        'h_mm': h_mm
    }

def main():
    cat_path = ROOT / 'modules/06_interior/extracts/bathroom-tiles-85.yaml'
    ocr_path = ROOT / '.gemini/antigravity-cli/brain/72709029-8bf0-4a8b-95ad-f7b12ee4e778/scratch/ocr_all.json'
    if not ocr_path.exists():
        ocr_path = Path('/root/.gemini/antigravity-cli/brain/72709029-8bf0-4a8b-95ad-f7b12ee4e778/scratch/ocr_all.json')
    
    ocr = json.loads(ocr_path.read_text(encoding='utf-8')) if ocr_path.exists() else {}
    data = yaml.safe_load(cat_path.read_text(encoding='utf-8'))
    tiles = data.get('tiles', [])
    print(f"Processing {len(tiles)} tiles...")
    
    tex_w, tex_h = 1024, 512 # 2:1 aspect for standard 120x60
    
    for idx, t in enumerate(tiles):
        slug = t['slug']
        img_name = t.get('source_image', '')
        ocr_txt = ocr.get(img_name, {}).get('text', '')
        info = classify_tile(t, ocr_txt)
        
        # Determine texture dimensions
        aspect = info['w_mm'] / max(1.0, info['h_mm'])
        if aspect >= 1.5:
            w, h = 1024, 512
        elif aspect <= 0.6:
            w, h = 512, 1024
        else:
            w, h = 1024, 1024
            
        seed = 1000 + idx * 37
        if info['mat'] == 'marble':
            arr = generate_marble_texture(w, h, info['base_rgb'], info['vein_rgb'], seed=seed)
        elif info['mat'] == 'onyx':
            arr = generate_onyx_texture(w, h, info['base_rgb'], info['vein_rgb'], seed=seed)
        elif info['mat'] == 'travertine':
            arr = generate_travertine_texture(w, h, info['base_rgb'], seed=seed)
        elif info['mat'] == 'wood':
            arr = generate_wood_texture(w, h, info['base_rgb'], seed=seed)
        elif info['mat'] == 'concrete':
            arr = generate_travertine_texture(w, h, info['base_rgb'], seed=seed)
        else:
            arr = generate_ceramic_texture(w, h, info['base_rgb'], is_glossy=info['is_glossy'], seed=seed)
            
        model_dir = ROOT / f"assets/models/tiles/{slug}"
        model_dir.mkdir(parents=True, exist_ok=True)
        tex_path = model_dir / "texture.jpg"
        
        img = Image.fromarray(arr)
        img.save(tex_path, format="JPEG", quality=95, optimize=True)
        
        # Write OBJ and MTL
        write_obj_and_mtl(model_dir, slug, info['w_mm'], info['h_mm'], thickness_mm=8.0)
        
        # Update tile catalog entry
        t['color_srgb'] = [round(c / 255.0, 3) for c in info['base_rgb']]
        t['roughness'] = info['roughness']
        t['coat'] = info['coat']
        t['coat_roughness'] = 0.18 if info['is_glossy'] else 0.35
        
        if (idx + 1) % 15 == 0 or idx == len(tiles) - 1:
            print(f"Generated clean PBR texture and OBJ for {idx+1}/{len(tiles)}: {slug} ({info['mat']})")
            
    cat_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print("Done generating all 85 clean tile models and textures!")

if __name__ == '__main__':
    main()
