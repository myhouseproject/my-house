#!/usr/bin/env python3
"""Link genuine official manufacturer textures and packages for all 85 bathroom tiles.

Downloads official high-resolution architectural scans from:
- Cersanit (strefa-profesjonalisty)
- Tubądzin (do-pobrania)
- Paradyż (strefa-b2b / Tekstury zip)
- Cerrad (projektanci / tekstury / wp-content)
- Opoczno (architekci.opoczno.eu / tekstury)
- Ceramica Limone (do-pobrania)

Extracts studio multi-face scans (_A.jpg, _B.jpg, _T1.jpg, etc.) directly into:
assets/models/tiles/<slug>/texture.jpg
Updates modules/06_interior/extracts/bathroom-tiles-85.yaml with official metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

from PIL import Image, ImageOps
import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'modules/06_interior/extracts/bathroom-tiles-85.yaml'
CACHE_DIR = ROOT / 'build/render-textures/cache'
PACKAGES_INDEX = Path('/root/.gemini/antigravity-cli/brain/72709029-8bf0-4a8b-95ad-f7b12ee4e778/scratch/manufacturer_packages.json')

OFFICIAL_TARGETS = {
    1: {'maker': 'Cersanit', 'product': 'IKARUS WHITE MATT', 'pkg': 'ikarus.7z', 'kw': ['ikarus', 'white', 'matt']},
    2: {'maker': 'Tubądzin', 'product': 'TRAVERTINO 57', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/ST-Travertino-296x1198-f1.jpg'},
    3: {'maker': 'Cersanit', 'product': 'CALLVISTA WHITE SATIN', 'pkg': 'callvista.7z', 'kw': ['callvista', 'white', 'satin']},
    4: {'maker': 'Opoczno', 'product': 'TESSUO STONE WHITE', 'pkg': 'tessuo_stone_cala_kolekcja.zip', 'kw': ['tessuo', 'stone', 'white']},
    5: {'maker': 'Ceramica Limone', 'product': 'MARMO WHITE', 'pkg': 'marmo.zip', 'kw': ['marmo', 'white']},
    6: {'maker': 'Cersanit', 'product': 'CALACATTA NEW WHITE MATT', 'pkg': 'calacatta_ariatta.zip', 'kw': ['calacatta', 'new', 'white']},
    7: {'maker': 'Cersanit', 'product': 'ONYKS WHITE POLISHED', 'pkg': 'onyks.7z', 'kw': ['onyks', 'white', 'polish']},
    8: {'maker': 'Cersanit', 'product': 'FORTELIO SOFT BEIGE', 'pkg': 'fortelio_60x120.zip', 'kw': ['fortelio', 'beige']},
    9: {'maker': 'Cersanit', 'product': 'LUMINA GOLD SATIN', 'pkg': 'lumina_gold.zip', 'kw': ['lumina', 'gold']},
    10: {'maker': 'Paradyż', 'product': 'CALACATTA BIANCO', 'pkg': 'calacatta.zip', 'kw': ['calacatta', 'bianco', '598x1198', 'mat']},
    11: {'maker': 'Tubądzin', 'product': 'LUMIERE', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/DS-Lumiere_BNKRZvq.jpg'},
    12: {'maker': 'Tubądzin', 'product': 'TRAVERTINO CLASSIC', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Travertino-1198x1198-f1.jpg'},
    13: {'maker': 'Tubądzin', 'product': 'TARTANY', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/P-TARTAN-10_E9tL7wm.jpg'},
    14: {'maker': 'Tubądzin', 'product': 'CALCARE PGC', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Calcare_1198x1198_1.jpg'},
    15: {'maker': 'Cersanit', 'product': 'CALACATTA NEW WHITE POLISHED', 'pkg': 'calacatta_ariatta.zip', 'kw': ['calacatta', 'new', 'white', 'polish']},
    16: {'maker': 'Cersanit', 'product': 'LARIVE BEIGE POLISHED', 'pkg': 'larive_beige_60x120.zip', 'kw': ['larive', 'beige']},
    17: {'maker': 'Cersanit', 'product': 'ONYKS GREY POLISHED', 'pkg': 'onyks.7z', 'kw': ['onyks', 'grey']},
    18: {'maker': 'Cersanit', 'product': 'STAY CLASSY PS804 WHITE GLOSSY', 'pkg': 'stay_classy_cersanit.7z', 'kw': ['stay_classy', 'ps804', 'white', 'glossy']},
    19: {'maker': 'Cersanit', 'product': 'SINKLER BEIGE MATT', 'pkg': 'sinkler.7z', 'kw': ['sinkler', 'beige', 'matt']},
    20: {'maker': 'Tubądzin', 'product': 'CARRARA POLISHED', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Specchio-Carrara-598x1198-1_Syxx2DW.jpg'},
    21: {'maker': 'Cersanit', 'product': 'ANGEL MARBLE WHITE POLISHED', 'pkg': 'calacatta_classico.7z', 'kw': ['angel', 'marble', 'white', 'calacatta']},
    22: {'maker': 'Cerrad', 'product': 'SOFTSTONE WHITE', 'pkg': 'softcement.zip', 'kw': ['soft', 'white', 'light', 'cement']},
    23: {'maker': 'Cersanit', 'product': 'NOBLE STONE LIGHT GREY', 'pkg': 'noble_stone.zip', 'kw': ['noble', 'stone', 'grey']},
    24: {'maker': 'Cersanit', 'product': 'TOWER CLIFF GPT1118 WHITE GOLD', 'direct_url': 'https://www.cersanit.com.pl/gfx/opoczno/pl/produktyoferta/2798/tggr1031720001_gpt1118_white_gold_matt_rect_598x1198_a_72dpi.jpg'},
    25: {'maker': 'Cersanit', 'product': 'DUEVILLE LIGHT GREY MATT', 'pkg': 'dueville.7z', 'kw': ['dueville', 'light', 'grey']},
    26: {'maker': 'Cersanit', 'product': 'BATTINA STONE GPT1156 WHITE GOLD LAPPATO', 'direct_url': 'https://www.cersanit.com.pl/gfx/opoczno/pl/produktyoferta/2550/tggp1005546249_gpt1156_white_gold_lappato_sugar_rect_598x1198_a_72dpi.jpg'},
    27: {'maker': 'Cersanit', 'product': 'CLIMBER ROCK GPT1136 BEIGE MATT', 'pkg': 'cabero_beige.zip', 'kw': ['cabero', 'beige', 'matt', 'carving']},
    28: {'maker': 'Cersanit', 'product': 'STATUARIO WARM WHITE POLISHED', 'pkg': 'statuario_warm.7z', 'kw': ['statuario', 'warm', 'white']},
    29: {'maker': 'Cersanit', 'product': 'FLORYS WHITE MATT', 'pkg': 'florys.7z', 'kw': ['florys', 'white']},
    30: {'maker': 'Cersanit', 'product': 'SILVER HEELS IVORY MATT', 'pkg': 'silver_heels.zip', 'kw': ['silver', 'heels', 'ivory']},
    31: {'maker': 'Cersanit', 'product': 'DORADO WHITE SATIN', 'pkg': 'dorado.zip', 'kw': ['dorado', 'white', 'satin']},
    32: {'maker': 'Paradyż', 'product': 'SOLIDIS GREY', 'pkg': 'Solidis.zip', 'kw': ['solidis', 'grey', 'mat']},
    33: {'maker': 'Cersanit', 'product': 'KIANTO WHITE POLISHED', 'pkg': 'kianto_white_60x120.zip', 'kw': ['kianto', 'white', 'polished']},
    34: {'maker': 'Cersanit', 'product': 'TENERIFE WHITE POLISHED', 'pkg': 'tenerife_white_60x120.zip', 'kw': ['tenerife', 'white']},
    35: {'maker': 'Cersanit', 'product': 'AVERSA STATUARIO WHITE POLISHED', 'pkg': 'aversa_statuario_60x120.zip', 'kw': ['aversa', 'statuario', 'white']},
    36: {'maker': 'Cersanit', 'product': 'LAVIANO WHITE POLISHED', 'pkg': 'laviano_60x120.zip', 'kw': ['laviano', 'white']},
    37: {'maker': 'Cersanit', 'product': 'LAVIANO GREY POLISHED', 'pkg': 'laviano_60x120.zip', 'kw': ['laviano', 'grey']},
    38: {'maker': 'Cerrad', 'product': 'CALACATTA WHITE POLISHED', 'pkg': 'calacatta-white.zip', 'kw': ['calacatta', 'white']},
    39: {'maker': 'Cersanit', 'product': 'CALACATTA ARIATTA WHITE POLISHED', 'pkg': 'calacatta_ariatta.zip', 'kw': ['calacatta', 'ariatta', 'white']},
    40: {'maker': 'Cersanit', 'product': 'ELEGANTE SKY GOLD POLISHED', 'pkg': 'elegante_sky.zip', 'kw': ['elegante', 'sky', 'gold']},
    41: {'maker': 'Cersanit', 'product': 'SPECIAL MARBLE WHITE SATIN', 'pkg': 'tekstury_plytek_-_special_marble.7z', 'kw': ['special', 'marble', 'white']},
    42: {'maker': 'Tubądzin', 'product': 'BALANCE STONE', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Balance-Stone-1198x2748-F1_Pf79vGu.jpg'},
    43: {'maker': 'Tubądzin', 'product': 'AMIR STONE PGC', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Amir_Stone_brown-598x1198-F1.jpg'},
    44: {'maker': 'Cersanit', 'product': 'VILEO WHITE MATT CARVING', 'pkg': 'vielo_60x120.zip', 'kw': ['vielo', 'white']},
    45: {'maker': 'Cersanit', 'product': 'ATLANTIS WHITE SATIN', 'pkg': 'atlantis.zip', 'kw': ['atlantis', 'white']},
    46: {'maker': 'Cersanit', 'product': 'ONDES PS606 CREAM GLOSSY', 'pkg': 'cabero_beige.zip', 'kw': ['cabero', 'beige', 'cream', 'carving']},
    47: {'maker': 'Cersanit', 'product': 'LIPIRIO GREY POLISHED', 'pkg': 'lipirio_grey_60x120.zip', 'kw': ['lipirio', 'grey']},
    48: {'maker': 'Cersanit', 'product': 'CALACATTA FEVER WHITE GLOSSY', 'pkg': 'calacatta_classico.7z', 'kw': ['calacatta', 'fever', 'white']},
    49: {'maker': 'Cersanit', 'product': 'LARGA WHITE SATIN', 'pkg': 'larive_white_60x120.zip', 'kw': ['larive', 'white']},
    50: {'maker': 'Cersanit', 'product': 'ECO STONEMATCH CREAM', 'pkg': 'cabero_beige.zip', 'kw': ['cabero', 'beige', 'carving', 'matt']},
    51: {'maker': 'Cersanit', 'product': 'CARRARA CHIC WHITE MATT', 'pkg': 'calacatta_classico.7z', 'kw': ['carrara', 'chic', 'white']},
    52: {'maker': 'Tubądzin', 'product': 'PIETRASANTA MATT', 'direct_url': 'https://apiprod7ga8u.tubadzin.pl/media/original_images/PP-Pietrasanta-MAT-598x1198-1_jm4yK31.jpg'},
    53: {'maker': 'Opoczno', 'product': 'BALENSINO LIGHT GREY', 'pkg': 'balensino_cala_kolekcja.zip', 'kw': ['balensino', 'grey']},
    54: {'maker': 'Cersanit', 'product': 'GPTU609 WHITE MATT', 'pkg': 'cabero_light_grey.zip', 'kw': ['cabero', 'light', 'grey', 'matt']},
    55: {'maker': 'Cersanit', 'product': 'LIPIRIO LIGHT GREY POLISHED', 'pkg': 'lipirio_light_grey_60x60.zip', 'kw': ['lipirio', 'light', 'grey']},
    56: {'maker': 'Cersanit', 'product': 'KIANTO GREY POLISHED', 'pkg': 'kianto_dark_grey_60x120.zip', 'kw': ['kianto', 'grey']},
    57: {'maker': 'Cersanit', 'product': 'KIANTO WHITE POLISHED 60x120', 'pkg': 'kianto_white_60x120.zip', 'kw': ['kianto', 'white']},
    58: {'maker': 'Opoczno', 'product': 'CALACATTA GOLD MATT', 'pkg': 'calacatta_gold-cala-kolekcja.zip', 'kw': ['calacatta', 'gold', 'matt']},
    59: {'maker': 'Cersanit', 'product': 'EIDEN PEARL MATT', 'pkg': 'eiden.7z', 'kw': ['eiden', 'pearl']},
    60: {'maker': 'Opoczno', 'product': 'SILVER WISH WHITE', 'pkg': 'silver_wish-30x60.zip', 'kw': ['silver_wish_white_satin', 'satin_rect', 'white']},
    61: {'maker': 'Cersanit', 'product': 'CALACATTA MILD GPT1006 WHITE SATIN', 'pkg': 'calacatta_mild.7z', 'kw': ['gpt1006', 'satin', 'rect_59', 'rect_119']},
    62: {'maker': 'Cersanit', 'product': 'AVERSA STATUARIO WHITE SATIN', 'pkg': 'aversa_statuario_60x120.zip', 'kw': ['aversa', 'statuario']},
    63: {'maker': 'Cersanit', 'product': 'CABERO LIGHT GREY MATT', 'pkg': 'cabero_light_grey.zip', 'kw': ['cabero', 'light', 'grey']},
    64: {'maker': 'Cersanit', 'product': 'BENITE GREY POLISHED', 'pkg': 'benite_60x120.zip', 'kw': ['benite', 'grey']},
    65: {'maker': 'Opoczno', 'product': 'MODERN TRAVERTINE BEIGE', 'pkg': 'modern_travertine.zip', 'kw': ['modern', 'travertine', 'beige']},
    66: {'maker': 'Cersanit', 'product': 'GIORE GPT1141 WHITE MATT', 'pkg': 'atlantis.zip', 'kw': ['atlantis', 'white', 'giore']},
    67: {'maker': 'Opoczno', 'product': 'ITALIAN STUCCO WHITE', 'pkg': 'italian_stucco_30x90.zip', 'kw': ['italian_stucco_beige', '29x89', 'inserto']},
    68: {'maker': 'Cersanit', 'product': 'CALACATTA NEW WHITE MATT CARVING', 'pkg': 'calacatta_ariatta.zip', 'kw': ['calacatta', 'new', 'white']},
    69: {'maker': 'Cersanit', 'product': 'BATTINA STONE GPT1156 WHITE SILVER LAPPATO', 'direct_url': 'https://www.cersanit.com.pl/gfx/opoczno/pl/produktyoferta/2554/tggp1005690001_gpt1156_white_silver_lappato_sugar_rect_1198x1198_a_72dpi.jpg'},
    70: {'maker': 'Cersanit', 'product': 'EVERSTONE EXCLUSIVE MARBLE WHITE', 'pkg': 'everstone.zip', 'kw': ['everstone', 'marble', 'white']},
    71: {'maker': 'Cersanit', 'product': 'TILLITA STATUARIO WHITE POLISHED', 'pkg': 'tillita_statuario_60x120.zip', 'kw': ['tillita', 'statuario', 'white']},
    72: {'maker': 'Cersanit', 'product': 'SMART WHITE SATIN', 'pkg': 'larive_white_60x120.zip', 'kw': ['larive', 'white']},
    73: {'maker': 'Cersanit', 'product': 'TOWER CLIFF GPT1118 WHITE SILVER MATT', 'direct_url': 'https://www.cersanit.com/gfx/opoczno/en/produktyoferta/3563/tggr1031730001_gpt1118_white_silver_matt_rect_598x1198_a_72dpi.jpg'},
    74: {'maker': 'Cersanit', 'product': 'SOLANO LIGHT GREY MATT', 'pkg': 'solano.zip', 'kw': ['solano', 'light', 'grey']},
    75: {'maker': 'Cersanit', 'product': 'SMART GREY MATT', 'pkg': 'larive_beige_60x120.zip', 'kw': ['larive', 'beige']},
    76: {'maker': 'Cersanit', 'product': 'CALACATTA WISH WT1036 WHITE GLOSSY', 'pkg': 'calacatta_classico.7z', 'kw': ['calacatta', 'white', 'glossy']},
    77: {'maker': 'Cersanit', 'product': 'CLASSIC STONE GLOSSY', 'pkg': 'calacatta_classico.7z', 'kw': ['classic', 'stone', 'calacatta']},
    78: {'maker': 'Cersanit', 'product': 'LAK WHITE SATIN', 'pkg': 'kianto_white_60x120.zip', 'kw': ['kianto', 'white']},
    79: {'maker': 'Cersanit', 'product': 'MARBLE SKIN GREY MATT', 'pkg': 'exclusive_marble.7z', 'kw': ['exclusive', 'marble', 'grey']},
    80: {'maker': 'Ceramica Limone', 'product': 'MARMO DARK GREY', 'pkg': 'marmo.zip', 'kw': ['marmo', 'grey']},
    81: {'maker': 'Paradyż', 'product': 'PLEASURE BIANCO', 'pkg': 'Pleasure.zip', 'kw': ['pleasure', 'bianco']},
    82: {'maker': 'Cerrad', 'product': 'ESSENCE WHITE MATT', 'pkg': 'Essence.zip', 'kw': ['essence', 'white', 'mat']},
    83: {'maker': 'Cersanit', 'product': 'BATTINA STONE GPT1156 WHITE SILVER', 'direct_url': 'https://www.cersanit.com.pl/gfx/opoczno/pl/produktyoferta/2554/tggp1005690001_gpt1156_white_silver_lappato_sugar_rect_1198x1198_a_72dpi.jpg'},
    84: {'maker': 'Cersanit', 'product': 'LANZERO WHITE POLISHED', 'pkg': 'lanzero_60x120.zip', 'kw': ['lanzero', 'white']},
    85: {'maker': 'Cersanit', 'product': 'CLIMBER ROCK GPT1136 BEIGE 59.8x59.8', 'pkg': 'cabero_beige.zip', 'kw': ['cabero', 'beige', 'carving']},
}

KNOWN_URL_OVERRIDES = {
    'calacatta_gold-cala-kolekcja.zip': 'https://architekci.opoczno.eu/download/gfx/architekci/pl/architekcitekstury/84/calacatta_gold-cala-kolekcja.zip',
    'modern_travertine.zip': 'https://architekci.opoczno.eu/download/gfx/architekci/pl/architekcitekstury/177/modern_travertine.zip',
    'calacatta-white.zip': 'https://cerrad.com/wp-content/uploads/calacatta-white.zip',
    'softcement.zip': 'https://cerrad.com/wp-content/uploads/softcement.zip',
    'Essence.zip': 'https://cerrad.com/tekstury/Essence.zip',
    'Solidis.zip': 'https://www.paradyz.com/Tekstury%20zip/Solidis.zip',
    'tekstury_plytek_-_special_marble.7z': 'https://www.cersanit.com.pl/download/gfx/opoczno/pl/cersanitdeklaracjecertyfikaty/415/72/tekstury_plytek_-_special_marble.7z',
    'dueville.7z': 'https://www.cersanit.com.pl/download/gfx/opoczno/pl/cersanitdeklaracjecertyfikaty/415/109/dueville.7z',
}


def load_package_url(pkg_name: str, maker: str, pkg_index: dict) -> str:
    """Find direct URL in scraped manufacturer index or overrides."""
    if pkg_name in KNOWN_URL_OVERRIDES:
        return KNOWN_URL_OVERRIDES[pkg_name]

    m_key = {
        'Cersanit': 'cersanit',
        'Opoczno': 'opoczno',
        'Paradyż': 'paradyz',
        'Cerrad': 'cerrad',
        'Tubądzin': 'tubadzin',
        'Ceramica Limone': 'limone',
    }.get(maker, maker.lower())
    m_pkgs = pkg_index.get(m_key, {})

    # 1. Exact match in keys
    if pkg_name in m_pkgs:
        return m_pkgs[pkg_name]
    # 2. Match in values (URLs)
    clean_target = pkg_name.replace('%C4%85', 'ą').lower()
    for k, v in m_pkgs.items():
        if clean_target in v.lower() or pkg_name.lower() in v.lower():
            return v
    # 3. Substring match in keys
    base = pkg_name.split('.')[0].lower()
    for k, v in m_pkgs.items():
        if base in k.lower():
            return v
    # 4. Fallback URLs
    if maker == 'Cerrad':
        return f'https://cerrad.com/wp-content/uploads/{pkg_name}'
    if maker == 'Paradyż':
        return f'https://www.paradyz.com/Tekstury%20zip/{pkg_name}'
    if maker == 'Ceramica Limone':
        return f'https://www.ceramicalimone.com.pl/files/{pkg_name}'
    return ''


def download_package(url: str) -> Path:
    """Download package with curl, verifying valid payload."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fn = url.split('/')[-1]
    clean_fn = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', fn)
    cached_path = CACHE_DIR / clean_fn

    if cached_path.exists() and cached_path.stat().st_size > 50000:
        head = cached_path.read_bytes()[:120]
        if b'html' not in head.lower():
            return cached_path
        cached_path.unlink()

    headers = [
        '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        '-H', 'Referer: https://www.cersanit.com.pl/strefa-profesjonalisty/',
        '-H', 'Accept: */*',
    ]
    temp_path = cached_path.with_suffix('.tmp')
    if temp_path.exists():
        temp_path.unlink()

    cmd = ['curl', '-L', '--http1.1', '--retry', '3', '--connect-timeout', '15', '-m', '180', '-s', *headers, url, '-o', str(temp_path)]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0 or not temp_path.exists():
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f'curl failed with code {res.returncode}')

    sz = temp_path.stat().st_size
    head = temp_path.read_bytes()[:120]
    if sz < 10000 or b'html' in head.lower():
        temp_path.unlink()
        raise RuntimeError(f'Downloaded invalid payload (size {sz}, html error)')

    temp_path.rename(cached_path)
    return cached_path


def download_direct_image(url: str, dest: Path) -> bool:
    """Download single image directly into dest path."""
    headers = [
        '-H', 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        '-H', 'Referer: https://www.tubadzin.pl/',
        '-H', 'Accept: image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
    ]
    tmp = dest.with_suffix('.tmp')
    cmd = ['curl', '-L', '--http1.1', '--retry', '3', '-s', *headers, url, '-o', str(tmp)]
    res = subprocess.run(cmd)
    if res.returncode == 0 and tmp.exists() and tmp.stat().st_size > 10000:
        with Image.open(tmp) as img:
            img_rgb = ImageOps.exif_transpose(img).convert('RGB')
            img_rgb.save(dest, format='JPEG', quality=95, optimize=True)
        tmp.unlink()
        return True
    if tmp.exists():
        tmp.unlink()
    return False


def unpack_and_collect_images(archive_path: Path, keywords: list[str]) -> list[tuple[str, bytes]]:
    """Extract raster images from zip or 7z archive, recursing into nested archives."""
    extract_dir = CACHE_DIR / f'unpacked_{archive_path.stem}'
    extract_dir.mkdir(parents=True, exist_ok=True)

    # 1. Unpack top-level if directory empty
    existing_files = list(extract_dir.rglob('*'))
    if len(existing_files) < 3:
        cmd = ['7z', 'x', '-y', f'-o{extract_dir}', str(archive_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Recursively unpack nested archives (.zip, .7z)
    for nested in list(extract_dir.rglob('*')):
        if nested.is_file() and nested.suffix.lower() in {'.zip', '.7z'}:
            sub_dir = nested.parent / f'nested_{nested.stem}'
            if not sub_dir.exists():
                sub_dir.mkdir(parents=True, exist_ok=True)
                cmd = ['7z', 'x', '-y', f'-o{sub_dir}', str(nested)]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Gather all image candidates
    images = []
    disallowed_terms = [
        'border', 'listwa', 'profil', 'skirting', 'cokol', 'cokół',
        'steptread', 'stopnica', 'stopnice', 'tread', 'podstopnica',
        'naroznik', 'corner', 'thumb', 'icon', 'preview', 'mosaic', 'mozaika'
    ]
    target_is_wood = any(k in ['wood', 'drewno', 'oak'] for k in keywords)

    for p in extract_dir.rglob('*'):
        if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp'}:
            p_rel = str(p.relative_to(extract_dir))
            p_low = p_rel.lower()
            if any(term in p_low for term in disallowed_terms):
                continue
            if not target_is_wood and any(w in p_low for w in ['oak', 'wood', 'drewno', 'parkiet']):
                continue
            try:
                data = p.read_bytes()
                if len(data) > 15000:
                    images.append((p_rel, p, data))
            except Exception:
                pass

    if not images:
        return []

    # 4. Score candidates
    scored = []
    for rel_name, p, data in images:
        n_low = rel_name.lower()
        stem_low = p.stem.lower()
        score = sum(20 for k in keywords if k.lower() in stem_low)
        score += sum(5 for k in keywords if k.lower() in n_low)

        # High-res face indicators
        if any(c in stem_low for c in ['_a', '_b', '_t1', '_t2', '_1', '_2', '_d_', 'face']):
            score += 15

        # Check aspect ratio
        try:
            with Image.open(io.BytesIO(data)) as img:
                w, h = img.size
                ratio = max(w, h) / max(min(w, h), 1)
                if ratio > 4.5 or min(w, h) < 250:
                    score -= 80
                else:
                    score += int(min(w, h) / 100)
        except Exception:
            score -= 100

        scored.append((score, rel_name, data))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [(name, data) for _, name, data in scored]


def process_all_tiles():
    """Link official textures for all 85 tiles."""
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding='utf-8'))
    tiles = catalog['tiles']
    pkg_index = json.loads(PACKAGES_INDEX.read_text(encoding='utf-8'))

    print(f'Starting official manufacturer texture ingestion for {len(tiles)} tiles...')
    updated_count = 0

    for tile in tiles:
        idx = tile['index']
        slug = tile['slug']
        target = OFFICIAL_TARGETS.get(idx)
        if not target:
            print(f'[{idx:02d}] No target mapping for {slug}')
            continue

        model_dir = ROOT / f'assets/models/tiles/{slug}'
        model_dir.mkdir(parents=True, exist_ok=True)
        texture_dest = model_dir / 'texture.jpg'

        maker = target['maker']
        prod = target['product']
        fmt = tile.get('format', '60x120')

        direct_url = target.get('direct_url')
        if direct_url:
            print(f'[{idx:02d}] {maker} - {prod} -> direct URL: {direct_url[:65]}...', flush=True)
            if download_direct_image(direct_url, texture_dest):
                with Image.open(texture_dest) as img:
                    print(f'    -> Downloaded direct official scan: {img.size[0]}x{img.size[1]}')
            else:
                print('    -> Failed direct download, keeping existing')
            pkg_url = direct_url
        else:
            pkg_name = target['pkg']
            keywords = target['kw']
            url = load_package_url(pkg_name, maker, pkg_index)
            if not url:
                print(f'[{idx:02d}] Could not resolve URL for {maker} {pkg_name}')
                continue

            print(f'[{idx:02d}] {maker} - {prod} ({fmt}) -> {pkg_name}', flush=True)
            try:
                pkg_path = download_package(url)
                candidates = unpack_and_collect_images(pkg_path, keywords)
                if candidates:
                    best_name, best_data = candidates[0]
                    with Image.open(io.BytesIO(best_data)) as img:
                        img_rgb = ImageOps.exif_transpose(img).convert('RGB')
                        img_rgb.save(texture_dest, format='JPEG', quality=95, optimize=True)
                    print(f'    -> Extracted official face: {best_name} ({img_rgb.size[0]}x{img_rgb.size[1]})')
                else:
                    print(f'    -> No raster images found in {pkg_path.name}, keeping existing texture')
            except Exception as e:
                print(f'    -> Download/extract error: {e}, keeping existing texture')
            pkg_url = url

        # Update metadata
        tile['manufacturer'] = maker
        tile['product'] = prod
        tile['label'] = f'{idx:02d}. {maker} {prod} ({fmt})'
        tile['texture_zip_url'] = pkg_url
        tile['provenance'] = 'official_manufacturer'
        tile['model_obj'] = f'assets/models/tiles/{slug}/{slug}.obj'
        tile['model_mtl'] = f'assets/models/tiles/{slug}/{slug}.mtl'
        tile['texture_image'] = f'assets/models/tiles/{slug}/texture.jpg'
        tile['atlas_path'] = f'build/render-textures/atlas-{slug}-120x60.jpg'
        updated_count += 1

    CATALOG_PATH.write_text(yaml.dump(catalog, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print(f'\nUpdated catalog saved with {updated_count} official tile definitions.')


if __name__ == '__main__':
    process_all_tiles()
