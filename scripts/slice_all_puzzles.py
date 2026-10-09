#!/usr/bin/env python3
"""Slice bathroom renders into 5 exact architectural puzzle pieces using Pillow.

Zones:
  1. podloga (Floor)
  2. sciana_lewa (Left Wall)
  3. sciana_srodkowa (Middle/Back Wall)
  4. sciana_prawa (Right Wall)
  5. sufit (Ceiling)
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path('/sdcard/Download/Dom_Lazienka_R07_Wszystkie')
DEFAULT_DST = Path('/sdcard/Download/Dom_Lazienka_R07_Puzzle')

MASK_ENTRANCE = ROOT / 'assets/masks/bathroom_entrance_zones_2000x1600.png'
MASK_REVERSE  = ROOT / 'assets/masks/bathroom_reverse_zones_2000x1600.png'

# Global cache for workers
_MASKS = {}


def load_masks(mask_path: Path):
    mask_img = Image.open(mask_path).convert('RGB')
    arr = np.array(mask_img)
    r = arr[:, :, 0] > 128
    g = arr[:, :, 1] > 128
    b = arr[:, :, 2] > 128
    return {
        'podloga': r & (~g) & (~b),
        'sciana_lewa': (~r) & g & (~b),
        'sciana_srodkowa': (~r) & (~g) & b,
        'sciana_prawa': r & g & (~b),
        'sufit': (~r) & g & b,
    }


def init_worker():
    global _MASKS
    _MASKS['entrance'] = load_masks(MASK_ENTRANCE)
    _MASKS['reverse'] = load_masks(MASK_REVERSE)


def process_file(task):
    fname, src_dir, dst_dir, cam, overwrite = task
    base_name = fname.replace('.png', '')
    src_path = Path(src_dir) / fname

    cam_masks = _MASKS[cam]
    if not overwrite:
        all_exist_and_clean = True
        for zone_name in cam_masks:
            out_file = Path(dst_dir) / cam / zone_name / f"{base_name}_{zone_name}.png"
            if not out_file.exists() or out_file.stat().st_size > 1_000_000:
                all_exist_and_clean = False
                break
        if all_exist_and_clean:
            return fname, 0

    try:
        with Image.open(src_path) as raw_img:
            img = raw_img.convert('RGBA')
    except Exception as e:
        return fname, -1

    img_arr = np.array(img)
    written = 0

    for zone_name, zone_mask in cam_masks.items():
        out_file = Path(dst_dir) / cam / zone_name / f"{base_name}_{zone_name}.png"
        if not overwrite and out_file.exists() and out_file.stat().st_size <= 1_000_000:
            continue

        piece = img_arr.copy()
        piece[~zone_mask] = 0
        piece_img = Image.fromarray(piece, 'RGBA')
        piece_img.save(out_file, compress_level=3)
        written += 1

    return fname, written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', type=Path, default=DEFAULT_SRC, help='Source folder with rendered PNGs')
    parser.add_argument('--dst', type=Path, default=DEFAULT_DST, help='Destination puzzle folder')
    parser.add_argument('--camera', choices=['entrance', 'reverse', 'both'], default='both')
    parser.add_argument('--workers', type=int, default=6, help='Number of parallel processes')
    parser.add_argument('--overwrite', action='store_true', help='Force regeneration of existing puzzle pieces')
    args = parser.parse_args()

    if not args.src.exists():
        print(f"Error: Source directory {args.src} does not exist", file=sys.stderr)
        sys.exit(1)

    # Find all images
    all_pngs = sorted([f for f in os.listdir(args.src) if f.endswith('.png')])
    has_dimmed = any('dimmed50' in f for f in all_pngs)
    if has_dimmed:
        pngs = [f for f in all_pngs if 'dimmed50' in f]
    else:
        pngs = all_pngs

    print(f"Found {len(pngs)} render files to slice.")

    # Create zone subdirectories
    zones = ['podloga', 'sciana_lewa', 'sciana_srodkowa', 'sciana_prawa', 'sufit']
    for cam in (['entrance', 'reverse'] if args.camera == 'both' else [args.camera]):
        for zone in zones:
            (args.dst / cam / zone).mkdir(parents=True, exist_ok=True)

    tasks = []
    for fname in pngs:
        cam = 'reverse' if 'reverse' in fname else 'entrance'
        if args.camera != 'both' and cam != args.camera:
            continue
        tasks.append((fname, str(args.src), str(args.dst), cam, args.overwrite))

    total = len(tasks)
    print(f"Slicing {total} renders using {args.workers} CPU workers...")

    done = 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker) as executor:
        futures = {executor.submit(process_file, t): t[0] for t in tasks}
        for future in as_completed(futures):
            fname, written = future.result()
            done += 1
            if done % 10 == 0 or done == total:
                print(f"[{done}/{total}] Processed: {fname}")

    print("Running termux-media-scan on puzzle output...")
    try:
        subprocess.run(['termux-media-scan', '-r', str(args.dst)], capture_output=True)
        print("Updated Android gallery index for puzzle pieces.")
    except Exception as exc:
        print(f"Notice: media-scan skipped ({exc})")

    total_pieces = sum(len(files) for _, _, files in os.walk(args.dst) if files)
    print(f"\nAll done! Total {total_pieces} puzzle pieces saved to: {args.dst}")


if __name__ == '__main__':
    main()
