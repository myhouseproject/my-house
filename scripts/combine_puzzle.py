#!/usr/bin/env python3
"""Seamlessly combine 5 puzzle pieces into a final high-resolution render using Pillow.

Usage examples:
    # Using tile numbers:
    python scripts/combine_puzzle.py --podloga 2 --sciana-lewa 1 --sciana-srodkowa 67 --sciana-prawa 22 --sufit 1

    # Using tile slugs/names:
    python scripts/combine_puzzle.py \
      --podloga 02_tub_dzin_travertino_57 \
      --sciana-srodkowa 01_cersanit_ikarus_white_matt \
      --sciana-lewa 04_opoczno_tile_04 \
      --sciana-prawa 22_cerrad_tile_22 \
      --sufit 01_cersanit_ikarus_white_matt \
      --output /sdcard/Download/moj_miks.png

    # Interactive mode:
    python scripts/combine_puzzle.py -i
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path('/sdcard/Download/Dom_Lazienka_R07_Wszystkie')
DEFAULT_PUZZLE = Path('/sdcard/Download/Dom_Lazienka_R07_Puzzle')
MASK_ENTRANCE = ROOT / 'assets/masks/bathroom_entrance_zones_2000x1600.png'
MASK_REVERSE  = ROOT / 'assets/masks/bathroom_reverse_zones_2000x1600.png'


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


def find_file_for_tile(src_dir: Path, tile_query: str, camera: str) -> Path:
    all_files = sorted([f for f in os.listdir(src_dir) if f.endswith('.png') and camera in f])
    q = str(tile_query).strip().lower()
    
    # 1. Exact file match
    for f in all_files:
        if f.lower() == q or f.lower() == f"{q}.png":
            return src_dir / f

    # 2. Number match: e.g. "2" or "02" matches "02_..."
    if q.isdigit():
        num_prefix = f"{int(q):02d}_"
        for f in all_files:
            if f.startswith(num_prefix):
                return src_dir / f

    # 3. Starts with prefix match (e.g. "02_")
    for f in all_files:
        if f.lower().startswith(f"{q}_"):
            return src_dir / f

    # 4. Substring in tile collection name
    for f in all_files:
        if q in f.lower():
            return src_dir / f

    raise FileNotFoundError(f"Nie znaleziono renderu pasującego do '{tile_query}' dla kamery '{camera}' w {src_dir}")


def find_puzzle_piece(puzzle_dir: Path, tile_query: str, camera: str, zone: str) -> Path:
    zone_dir = puzzle_dir / camera / zone
    if not zone_dir.exists():
        raise FileNotFoundError(f"Folder puzzli nie istnieje: {zone_dir}")
    all_files = sorted([f for f in os.listdir(zone_dir) if f.endswith('.png')])
    q = str(tile_query).strip().lower()

    if q.isdigit():
        num_prefix = f"{int(q):02d}_"
        for f in all_files:
            if f.startswith(num_prefix):
                return zone_dir / f

    for f in all_files:
        if f.lower().startswith(f"{q}_"):
            return zone_dir / f

    for f in all_files:
        if q in f.lower():
            return zone_dir / f

    raise FileNotFoundError(f"Nie znaleziono części puzzla '{zone}' dla zapytania '{tile_query}' w {zone_dir}")


def interactive_prompt(args):
    print("\n=== KREATOR KOMPOZYCJI PUZZLI ŁAZIENKI ===")
    cam_in = input("Wybierz ujęcie (1: wejście [domyślne], 2: odwrócone): ").strip()
    args.camera = 'reverse' if cam_in == '2' else 'entrance'

    print(f"\nUjęcie: {args.camera.upper()}")
    print("Podaj numery płytek (np. 1..85) lub nazwy kolekcji:")
    
    args.podloga = input("Podłoga [np. 02]: ").strip() or "02"
    args.sciana_lewa = input("Ściana lewa [np. 01]: ").strip() or "01"
    args.sciana_srodkowa = input("Ściana środkowa [np. 67]: ").strip() or "67"
    args.sciana_prawa = input("Ściana prawa [np. 22]: ").strip() or "22"
    args.sufit = input(f"Sufit [Enter = jak środkowa ({args.sciana_srodkowa})]: ").strip() or args.sciana_srodkowa


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--src', type=Path, default=DEFAULT_SRC, help='Folder z pełnymi renderami')
    parser.add_argument('--puzzle-dir', type=Path, default=DEFAULT_PUZZLE, help='Folder z wyciętymi puzzlami')
    parser.add_argument('--camera', choices=['entrance', 'reverse'], default='entrance', help='Kąt kamery')
    parser.add_argument('--podloga', '--floor', help='Numer lub nazwa płytki na podłogę')
    parser.add_argument('--sciana-lewa', '--wall-left', help='Numer lub nazwa płytki na ścianę lewą')
    parser.add_argument('--sciana-srodkowa', '--wall-mid', help='Numer lub nazwa płytki na ścianę środkową')
    parser.add_argument('--sciana-prawa', '--wall-right', help='Numer lub nazwa płytki na ścianę prawą')
    parser.add_argument('--sufit', '--ceiling', default=None, help='Numer lub nazwa płytki na sufit')
    parser.add_argument('--output', '-o', type=Path, default=None, help='Ścieżka do pliku wyjściowego PNG')
    parser.add_argument('-i', '--interactive', action='store_true', help='Tryb interaktywny z pytaniami')
    parser.add_argument('--from-puzzle', action='store_true', help='Składaj bezpośrednio z wyciętych kawałków PNG')
    args = parser.parse_args()

    if args.interactive or not (args.podloga and args.sciana_lewa and args.sciana_srodkowa and args.sciana_prawa):
        interactive_prompt(args)

    if not args.sufit:
        args.sufit = args.sciana_srodkowa

    selections = {
        'podloga': args.podloga,
        'sciana_lewa': args.sciana_lewa,
        'sciana_srodkowa': args.sciana_srodkowa,
        'sciana_prawa': args.sciana_prawa,
        'sufit': args.sufit,
    }

    if args.output is None:
        p_tag = str(args.podloga).replace(' ', '_')
        l_tag = str(args.sciana_lewa).replace(' ', '_')
        m_tag = str(args.sciana_srodkowa).replace(' ', '_')
        r_tag = str(args.sciana_prawa).replace(' ', '_')
        out_name = f"lazienka_{args.camera}_P{p_tag}_L{l_tag}_M{m_tag}_R{r_tag}.png"
        args.output = Path('/sdcard/Download') / out_name

    print(f"\nSkładanie renderu ({args.camera}):")
    print(f"  • Podłoga:         {args.podloga}")
    print(f"  • Ściana lewa:     {args.sciana_lewa}")
    print(f"  • Ściana środkowa: {args.sciana_srodkowa}")
    print(f"  • Ściana prawa:    {args.sciana_prawa}")
    print(f"  • Sufit:           {args.sufit}")

    if args.from_puzzle and args.puzzle_dir.exists():
        combined = Image.new('RGBA', (2000, 1600), (0, 0, 0, 0))
        for zone_name, query in selections.items():
            piece_path = find_puzzle_piece(args.puzzle_dir, query, args.camera, zone_name)
            print(f"  [puzzle] Wklejam {zone_name:15s} <- {piece_path.name}")
            with Image.open(piece_path) as p_img:
                combined.alpha_composite(p_img)
        res_img = combined.convert('RGB')
    else:
        mask_file = MASK_REVERSE if args.camera == 'reverse' else MASK_ENTRANCE
        masks = load_masks(mask_file)
        combined_arr = np.zeros((1600, 2000, 3), dtype=np.uint8)

        for zone_name, query in selections.items():
            file_path = find_file_for_tile(args.src, query, args.camera)
            print(f"  [render] Wklejam {zone_name:15s} <- {file_path.name}")
            img_arr = np.array(Image.open(file_path).convert('RGB'))
            m = masks[zone_name]
            combined_arr[m] = img_arr[m]
        res_img = Image.fromarray(combined_arr, 'RGB')

    args.output.parent.mkdir(parents=True, exist_ok=True)
    res_img.save(args.output, compress_level=3)
    print(f"\nSukces! Wygenerowano plik: {args.output}")

    try:
        subprocess.run(['termux-media-scan', str(args.output)], capture_output=True)
        print("Zaktualizowano galerię Androida (obrazek widoczny w Galerii).")
    except Exception as exc:
        pass


if __name__ == '__main__':
    main()
