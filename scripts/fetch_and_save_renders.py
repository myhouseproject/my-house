#!/usr/bin/env python3
"""Download rendered HQ images from GitHub Actions and save them to the phone gallery.

Usage:
    python scripts/fetch_and_save_renders.py [--run-id <ID>] [--watch]
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PHONE_DOWNLOADS = Path('/sdcard/Download/Dom_Lazienka_R07_Wszystkie')
PHONE_PICTURES = Path('/sdcard/Pictures/Dom_Lazienka_R07_HQ')
LOCAL_RENDERS = ROOT / 'renders/bathroom_85'


def get_latest_run_id():
    cmd = ['gh', 'run', 'list', '--workflow', 'Porównanie płytek łazienki R07', '-L', '1', '--json', 'databaseId,status,conclusion']
    res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=True)
    runs = json.loads(res.stdout)
    if not runs:
        raise RuntimeError('No workflow runs found for Porównanie płytek łazienki R07')
    return runs[0]['databaseId'], runs[0]['status'], runs[0].get('conclusion')


def download_and_save(run_id):
    PHONE_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    PHONE_PICTURES.mkdir(parents=True, exist_ok=True)
    LOCAL_RENDERS.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path('/tmp') / f'gh_artifacts_{run_id}'
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f'Downloading artifacts for run {run_id} into {tmp_dir}...')
    env = dict(os.environ, TMPDIR='/tmp')
    cmd = ['gh', 'run', 'download', str(run_id), '--dir', str(tmp_dir)]
    subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)

    images = list(tmp_dir.rglob('*.png'))
    print(f'Found {len(images)} rendered PNG images.')

    from PIL import Image

    saved_count = 0
    for img in sorted(images):
        # Verify image integrity
        try:
            with Image.open(img) as pil_check:
                pil_check.verify()
        except Exception as verify_err:
            print(f'Skipping corrupted image {img.name}: {verify_err}')
            continue

        dest_local = LOCAL_RENDERS / img.name
        dest_dl = PHONE_DOWNLOADS / img.name
        dest_pic = PHONE_PICTURES / img.name

        try:
            shutil.copyfile(img, dest_local)
            shutil.copyfile(img, dest_dl)
            shutil.copyfile(img, dest_pic)
            saved_count += 1
        except Exception as copy_err:
            print(f'Error copying {img.name}: {copy_err}')

    os.sync()
    print(f'Successfully copied and synced {saved_count} images to:')
    print(f'  1. {PHONE_DOWNLOADS}')
    print(f'  2. {PHONE_PICTURES}')
    print(f'  3. {LOCAL_RENDERS}')

    # Media scan so Android Gallery immediately indexes new pictures
    try:
        subprocess.run(['termux-media-scan', str(PHONE_DOWNLOADS), str(PHONE_PICTURES)], capture_output=True)
        print('Executed termux-media-scan: photos are now live in phone gallery.')
    except Exception as exc:
        print(f'Notice: termux-media-scan skipped ({exc})')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', type=int, help='GitHub run ID to download')
    parser.add_argument('--watch', action='store_true', help='Watch the run until complete')
    args = parser.parse_args()

    run_id = args.run_id
    if not run_id:
        run_id, status, conclusion = get_latest_run_id()
        print(f'Latest run: ID {run_id} (status: {status}, conclusion: {conclusion})')
    else:
        status, conclusion = 'unknown', 'unknown'

    if args.watch:
        print(f'Watching run {run_id}...')
        downloaded_artifacts = set()
        while True:
            try:
                cmd = ['gh', 'run', 'view', str(run_id), '--json', 'status,conclusion']
                res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
                if res.returncode == 0:
                    info = json.loads(res.stdout)
                    status, conclusion = info['status'], info.get('conclusion')
                    print(f'Run status: {status} ({conclusion})')
                    if status == 'completed':
                        break
            except Exception as e:
                print(f'Transient run check error: {e}')
            
            # Check for newly uploaded render artifacts
            try:
                cmd_art = ['gh', 'api', f'repos/rutkala/dom/actions/runs/{run_id}/artifacts', '--jq', '.artifacts[] | .name']
                res_art = subprocess.run(cmd_art, cwd=str(ROOT), capture_output=True, text=True)
                if res_art.returncode == 0:
                    current_arts = set(line.strip() for line in res_art.stdout.splitlines() if line.strip().startswith('bathroom-R07-'))
                    new_arts = current_arts - downloaded_artifacts
                    if new_arts:
                        print(f'Detected {len(new_arts)} new render artifact(s): {list(new_arts)[:3]}...')
                        download_and_save(run_id)
                        downloaded_artifacts.update(current_arts)
            except Exception as e:
                print(f'Notice during artifact check: {e}')
                
            time.sleep(30)

    download_and_save(run_id)


if __name__ == '__main__':
    main()
