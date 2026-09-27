#!/usr/bin/env python3
"""Download the two pinned PROJ datum grids needed for Google exports."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

from google_geodesy import GRID_DIRECTORY, GRID_SOURCES


def prepare_grid(source: dict) -> Path:
    GRID_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = GRID_DIRECTORY / source["file"]
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == source["sha256"]:
        print(f"Verified {destination.name}")
        return destination

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=source["file"]+".", suffix=".download",
                                         dir=GRID_DIRECTORY, delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            with urlopen(source["url"], timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != source["sha256"]:
            raise RuntimeError(f"Downloaded grid checksum mismatch: {source['file']}")
        temporary.replace(destination)
        print(f"Downloaded and verified {destination.name}")
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    for source in GRID_SOURCES:
        prepare_grid(source)


if __name__ == "__main__":
    main()
