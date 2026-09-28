#!/usr/bin/env python3
"""Regenerate the legacy JSON snapshot from the declarative house_3d YAML."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_config import load_house_3d_params

TARGET = ROOT / "parametry_modelu.json"


def main():
    params = load_house_3d_params()
    TARGET.write_text(
        json.dumps(params, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Zapisano snapshot kompatybilności: {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
