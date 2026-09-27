#!/usr/bin/env python3
"""Rebuild portal outputs from the checked-in scene without rerunning CAD/garden generation."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BUILD_STEPS = (
    'uaktualnij_teren_i_otoczenie.py',
    'export_scene_downloads.py',
    'eksportuj_google_earth.py',
    'aktualizuj_podglad.py',
)


def main():
    for script in BUILD_STEPS:
        print(f'Przebudowa: {script}', flush=True)
        subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT, check=True)
    print('Gotowe: portal, podgląd offline, GLB wnętrza/bryły oraz pliki Google są zgodne z aktualną sceną.')


if __name__ == '__main__':
    main()
