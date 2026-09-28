"""Shared loader for declarative project configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parent

MODULE_FILES = {
    "map": ROOT / "modules" / "01_map" / "model.yaml",
    "terrain": ROOT / "modules" / "02_terrain" / "model.yaml",
    "house_2d": ROOT / "modules" / "03_house_2d" / "model.yaml",
    "house_3d": ROOT / "modules" / "04_house_3d" / "model.yaml",
    "finishes": ROOT / "modules" / "05_finishes" / "model.yaml",
    "interior": ROOT / "modules" / "06_interior" / "model.yaml",
    "garden": ROOT / "modules" / "07_garden" / "model.yaml",
}


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_module_model(module_id: str) -> dict[str, Any]:
    path = MODULE_FILES[module_id]
    model = load_yaml(path)
    if model.get("schema_version") != 1:
        raise ValueError(f"Unsupported {module_id} schema_version")
    if model.get("module") != module_id:
        raise ValueError(f"Invalid module id in {path}")
    return model


def load_map_config() -> dict[str, Any]:
    return load_module_model("map")["config"]


def load_terrain_model() -> dict[str, Any]:
    return load_module_model("terrain")


def load_house_2d_model() -> dict[str, Any]:
    return load_module_model("house_2d")


def load_house_3d_model() -> dict[str, Any]:
    return load_module_model("house_3d")


def load_house_3d_params() -> dict[str, Any]:
    return load_house_3d_model()["parameters"]


def load_finishes_model() -> dict[str, Any]:
    return load_module_model("finishes")


def load_interior_model() -> dict[str, Any]:
    return load_module_model("interior")


def load_garden_model() -> dict[str, Any]:
    return load_module_model("garden")
