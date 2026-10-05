#!/usr/bin/env python3
"""Batch render of the 6 Calacatta bathroom variants and formats."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDERS_DIR = ROOT / 'renders'
DOWNLOADS_DIR = Path('/sdcard/Download/Dom_Lazienka_R07')
DOWNLOADS_DIR_NEW = Path('/sdcard/Download/Dom_Lazienka_R07_NOWE')
ARTIFACT_DIR = Path('/root/.gemini/antigravity-cli/brain/659416f5-5ec6-4e6c-9ac7-94df641ddcf3')

JOBS = [
    {
        'filename': 'R07_Calacatta_Marble_120x60_GW',
        'variant': 'opoczno_calacatta_marble',
        'format': '120x60',
        'description': 'Opoczno Calacatta Marble - format klasyczny 120x60 cm'
    },
    {
        'filename': 'R07_Calacatta_Marble_120x120_GW',
        'variant': 'opoczno_calacatta_marble',
        'format': '120x120',
        'description': 'Opoczno Calacatta Marble - format kwadratowy 120x120 cm'
    },
    {
        'filename': 'R07_Calacatta_Marble_120x280_GW',
        'variant': 'opoczno_calacatta_marble',
        'format': '120x280',
        'description': 'Opoczno Calacatta Marble - wielki format / slaby 120x280 cm'
    },
    {
        'filename': 'R07_Calacatta_Paonazzo_czarno_zlota_GW',
        'variant': 'opoczno_calacatta_paonazzo',
        'format': '120x60',
        'description': 'Opoczno Calacatta Paonazzo - czarno-złota żyła dramatyczna'
    },
    {
        'filename': 'R07_Calacatta_Monet_GW',
        'variant': 'opoczno_calacatta_monet',
        'format': '120x60',
        'description': 'Opoczno Calacatta Monet - grafitowo-złota subtelna'
    },
    {
        'filename': 'R07_Calacatta_Gold_GW',
        'variant': 'opoczno_calacatta_gold',
        'format': '120x60',
        'description': 'Opoczno Calacatta Gold - ciepłe złocisto-szare użylenie'
    },
]

def main():
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR_NEW.mkdir(parents=True, exist_ok=True)
    
    total_jobs = len(JOBS)
    print(f'Starting batch render of {total_jobs} Calacatta bathroom views...')
    start_all = time.time()
    
    for idx, job in enumerate(JOBS, 1):
        print(f"\n[{idx}/{total_jobs}] Rendering: {job['filename']} ({job['description']})...", flush=True)
        t0 = time.time()
        tmp_out = Path(f"/tmp/render_job_{job['filename']}")
        tmp_out.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            'blender', '--background', '--python', 'scripts/render_bathroom.py', '--',
            '--scene', 'build/current/scena_lokalna.json',
            '--config', 'modules/06_interior/extracts/bathroom-render.yaml',
            '--output', str(tmp_out),
            '--quality', 'preview',
            '--tile-variant', job['variant'],
            '--tile-format', job['format'],
            '--camera', 'entrance',
        ]
        
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error rendering {job['filename']}:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
            sys.exit(res.returncode)
            
        src_png = tmp_out / 'bathroom-entrance-preview.png'
        if not src_png.exists():
            print(f"Error: expected output {src_png} not found!", file=sys.stderr)
            sys.exit(1)
            
        target_name = f"{job['filename']}.png"
        
        # 1. Repo renders/
        dest_repo = RENDERS_DIR / target_name
        shutil.copy2(src_png, dest_repo)
        
        # 2. Phone Downloads folder (existing)
        dest_phone = DOWNLOADS_DIR / target_name
        shutil.copy2(src_png, dest_phone)
        
        # 3. Phone Downloads folder (new clean folder to bust Android thumbnail cache)
        dest_phone_new = DOWNLOADS_DIR_NEW / target_name
        shutil.copy2(src_png, dest_phone_new)

        # 4. Artifact directory
        dest_art = ARTIFACT_DIR / target_name
        shutil.copy2(src_png, dest_art)
        
        try:
            subprocess.run(['termux-media-scan', str(dest_phone), str(dest_phone_new)], capture_output=True)
        except Exception:
            pass

        dt = time.time() - t0
        print(f"[{idx}/{total_jobs}] Finished {target_name} in {dt:.1f}s -> Saved to repo, phone, and artifacts.", flush=True)
        
    print(f"\nAll {total_jobs} renders completed successfully in {time.time()-start_all:.1f}s!", flush=True)

if __name__ == '__main__':
    main()
