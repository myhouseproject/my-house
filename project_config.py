"""Shared loader for declarative project configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parent
HOUSE_3D_MODEL = ROOT / "modules" / "04_house_3d" / "model.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_house_3d_model() -> dict[str, Any]:
    model = load_yaml(HOUSE_3D_MODEL)
    if model.get("schema_version") != 1:
        raise ValueError("Unsupported house_3d schema_version")
    if model.get("module") != "house_3d":
        raise ValueError("Invalid house_3d module id")
    if not isinstance(model.get("parameters"), dict):
        raise ValueError("house_3d model.yaml must contain parameters mapping")
    return model


def load_house_3d_params() -> dict[str, Any]:
    return load_house_3d_model()["parameters"]
