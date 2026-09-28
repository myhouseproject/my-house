#!/usr/bin/env python3
"""Regenerate legacy JSON compatibility snapshots from declarative module YAMLs."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_config import (
    load_map_config,
    load_terrain_model,
    load_house_2d_model,
    load_house_3d_params,
    load_finishes_model,
    load_interior_model,
)


def write_json(relative_path: str, data) -> None:
    target = ROOT / relative_path
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Zapisano snapshot kompatybilności: {relative_path}")


def main():
    terrain = load_terrain_model()
    house_2d = load_house_2d_model()
    finishes = load_finishes_model()
    interior = load_interior_model()

    snapshots = {
        "geoportal_georef.json": load_map_config(),
        "pzt_zagospodarowanie.json": terrain["site"],
        "context_geometry_source.json": terrain["context_geometry"],
        "dane_zrodlowe.json": house_2d["source_data"],
        "obrys_dachu_z_pdf.json": house_2d["roof"],
        "okna_projektowe.json": house_2d["windows"],
        "stolarka_zewnetrzna.json": house_2d["external_joinery"],
        "parametry_modelu.json": load_house_3d_params(),
        "elewacje_materialy.json": finishes["elevations"],
        "wnetrze_projekt.json": interior["project"],
    }
    for path, data in snapshots.items():
        write_json(path, data)


if __name__ == "__main__":
    main()
