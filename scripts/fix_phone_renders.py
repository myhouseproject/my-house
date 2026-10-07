#!/usr/bin/env python3
"""Fix corrupted renders and complete download of all 85 bathroom renders to phone."""
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed

PHONE_PICTURES = Path('/sdcard/Pictures/Dom_Lazienka_R07_HQ')
PHONE_DOWNLOADS = Path('/sdcard/Download/Dom_Lazienka_R07_Wszystkie')
LOCAL_RENDERS = Path('/root/dom/renders/bathroom_85')

PHONE_PICTURES.mkdir(parents=True, exist_ok=True)
PHONE_DOWNLOADS.mkdir(parents=True, exist_ok=True)
LOCAL_RENDERS.mkdir(parents=True, exist_ok=True)

RUN_ID = 37502209645
env = dict(os.environ, TMPDIR='/tmp')

def check_valid_png(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False

# Step 1: Clean up corrupted files from phone
print("Checking and cleaning corrupted files on phone...")
for d in [PHONE_PICTURES, PHONE_DOWNLOADS]:
    for png in list(d.glob('*.png')):
        if not check_valid_png(png):
            print(f"Removing corrupted file: {png}")
            png.unlink()

# Step 2: List all required artifacts from GitHub Actions run
cmd = ['gh', 'api', f'repos/rutkala/dom/actions/runs/{RUN_ID}/artifacts', '--paginate', '--jq', '.artifacts[] | .name']
res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
artifact_names = [line.strip() for line in res.stdout.splitlines() if line.strip().startswith('bathroom-R07-')]
print(f"Total bathroom render artifacts on GitHub: {len(artifact_names)}")

def download_one(name):
    slug = name.replace('bathroom-R07-', '')
    p1 = PHONE_PICTURES / f"{slug}_entrance.png"
    p2 = PHONE_PICTURES / f"{slug}_reverse.png"
    
    # If both already valid on phone and local, skip
    if check_valid_png(p1) and check_valid_png(p2):
        d1 = PHONE_DOWNLOADS / f"{slug}_entrance.png"
        d2 = PHONE_DOWNLOADS / f"{slug}_reverse.png"
        if not check_valid_png(d1):
            shutil.copyfile(p1, d1)
        if not check_valid_png(d2):
            shutil.copyfile(p2, d2)
        return name, 0, "already_valid"

    tmp_dir = Path(f"/tmp/pdl_{name}")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    cmd = ['gh', 'run', 'download', str(RUN_ID), '-n', name, '--dir', str(tmp_dir)]
    sub_res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if sub_res.returncode != 0:
        return name, 0, f"error: {sub_res.stderr.strip()[:100]}"

    copied = 0
    pngs = list(tmp_dir.glob('*.png'))
    for png in pngs:
        if check_valid_png(png):
            # Write to local first
            local_target = LOCAL_RENDERS / png.name
            shutil.copyfile(png, local_target)
            
            # Copy to phone targets safely
            p_target = PHONE_PICTURES / png.name
            d_target = PHONE_DOWNLOADS / png.name
            shutil.copyfile(png, p_target)
            shutil.copyfile(png, d_target)
            copied += 1
        else:
            print(f"Warning: downloaded {png} in {name} is not a valid PNG!")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    return name, copied, "success"

print("Starting robust download with 4 workers...")
downloaded_count = 0
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = {executor.submit(download_one, name): name for name in artifact_names}
    for future in as_completed(futures):
        name, count, status = future.result()
        if count > 0:
            downloaded_count += count
            print(f"Downloaded & saved {name} ({count} images)")
        elif status != "already_valid":
            print(f"Status for {name}: {status}")

os.sync()
print(f"Download complete! Newly saved: {downloaded_count} images.")

# Step 3: Final verification of all phone files
valid_p = sum(1 for f in PHONE_PICTURES.glob('*.png') if check_valid_png(f))
valid_d = sum(1 for f in PHONE_DOWNLOADS.glob('*.png') if check_valid_png(f))
print(f"Phone Pictures valid PNGs: {valid_p}/170")
print(f"Phone Downloads valid PNGs: {valid_d}/170")

try:
    subprocess.run(['termux-media-scan', str(PHONE_PICTURES), str(PHONE_DOWNLOADS)], check=True)
    print("termux-media-scan completed successfully!")
except Exception as e:
    print(f"termux-media-scan: {e}")
