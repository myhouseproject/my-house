#!/usr/bin/env python3
"""Compatibility command for the canonical build; never reuses stale scene exports."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'build.py'),
                    '--scope', 'full', *sys.argv[1:]], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
