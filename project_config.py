"""Shared loader for declarative project configuration."""
from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import math
import operator
from pathlib import Path
from typing import Any
import yaml

ROOT = Path(__file__).resolve().parent
PROVENANCE_TYPES = {"project", "measured", "ordered", "assumed", "derived"}
DECISION_STATES = {"pending_measurement", "pending_decision", "resolved"}


class _UniqueKeyLoader(yaml.SafeLoader):
    """A duplicated YAML key must not silently override an architectural decision."""


def _unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)

MODULE_FILES = {
    "map": ROOT / "modules" / "01_map" / "model.yaml",
    "terrain": ROOT / "modules" / "02_terrain" / "model.yaml",
    "house_2d": ROOT / "modules" / "03_house_2d" / "model.yaml",
    "house_3d": ROOT / "modules" / "04_house_3d" / "model.yaml",
    "finishes": ROOT / "modules" / "05_finishes" / "model.yaml",
    "interior": ROOT / "modules" / "06_interior" / "model.yaml",
    "garden": ROOT / "modules" / "07_garden" / "model.yaml",
}


def cached_input_path(root: Path, name: str) -> Path:
    """Build staging uses root inputs; the checkout keeps downloaded caches in data/."""
    root = Path(root)
    direct = root / name
    return direct if direct.is_file() else root / "data" / name


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def _read_model(path: Path) -> dict[str, Any]:
    """Compose explicit local extracts; never fetch or execute a source reference."""
    model = load_yaml(path)
    for key, relative in model.pop("includes", {}).items():
        if key in model:
            raise ValueError(f"{path}: include duplicates editable key {key}")
        included = (path.parent / relative).resolve()
        if not included.is_relative_to(path.parent.resolve()):
            raise ValueError(f"{path}: include must stay in its module: {relative}")
        value = yaml.load(included.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        if not isinstance(value, (dict, list)):
            raise ValueError(f"{included}: expected mapping or list")
        model[key] = value
    return model


def _get_path(data: dict, path: str):
    value = data
    for key in path.split("."):
        value = value[key]
    return value


def _set_path(data: dict, path: str, value):
    parent = data
    *parts, key = path.split(".")
    for part in parts:
        parent = parent.setdefault(part, {})
    parent[key] = value


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def resolve_parameters(model: dict[str, Any]) -> dict[str, Any]:
    """Resolve a deliberately small arithmetic grammar, including dependency cycles.

    Derived fields cannot also contain literal values. No Python eval, calls or
    indexing are allowed; formulas consist of parameter paths and + - * / only.
    """
    values = deepcopy(model["parameters"])
    formulas = model.get("derived_parameters", {})
    visiting = set()
    operators = {ast.Add: operator.add, ast.Sub: operator.sub,
                 ast.Mult: operator.mul, ast.Div: operator.truediv}

    def path_for(node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return path_for(node.value) + "." + node.attr
        raise ValueError("Derived formula expects a parameter path")

    def evaluate(node):
        if isinstance(node, (ast.Name, ast.Attribute)):
            key = path_for(node)
            return resolve(key) if key in formulas else _get_path(values, key)
        if isinstance(node, ast.Constant) and _numeric(node.value):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            left, right = evaluate(node.left), evaluate(node.right)
            if not _numeric(left) or not _numeric(right):
                raise ValueError("Derived formula requires numeric parameters")
            return operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return (-1 if isinstance(node.op, ast.USub) else 1) * evaluate(node.operand)
        raise ValueError("Unsupported derived formula; only arithmetic is allowed")

    resolved = set()

    def resolve(key):
        if key in resolved:
            return _get_path(values, key)
        if key in visiting:
            raise ValueError(f"Derived parameter cycle at {key}")
        try:
            _get_path(values, key)
        except KeyError:
            pass
        else:
            raise ValueError(f"Derived parameter {key} also has a literal value")
        visiting.add(key)
        rule = formulas[key]
        value = evaluate(ast.parse(rule["expression"], mode="eval").body)
        if not _numeric(value):
            raise ValueError(f"Non-finite derived parameter {key}")
        if "round_digits" in rule:
            value = round(value, rule["round_digits"])
        _set_path(values, key, value)
        resolved.add(key)
        visiting.remove(key)
        return value

    for key in formulas:
        resolve(key)
    return values


def load_module_model(module_id: str) -> dict[str, Any]:
    path = MODULE_FILES[module_id]
    model = _read_model(path)
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
    model = load_module_model("house_3d")
    model["parameters"] = resolve_parameters(model)
    return model


def load_house_3d_params() -> dict[str, Any]:
    return load_house_3d_model()["parameters"]


def load_finishes_model() -> dict[str, Any]:
    return load_module_model("finishes")


def load_interior_model() -> dict[str, Any]:
    model = load_module_model("interior")
    # Room extracts own their palettes; expose one canonical material registry.
    for room in (model.get("small_bathroom", {}),):
        for key in ("render_materials", "material_properties"):
            additions = room.get(key, {})
            overlap = set(additions) & set(model.get(key, {}))
            if overlap:
                raise ValueError(f"Duplicate interior {key}: {sorted(overlap)}")
            model.setdefault(key, {}).update(additions)
    return model


def load_garden_model() -> dict[str, Any]:
    return load_module_model("garden")


def load_decision_register() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "decisions.yaml")


def load_room_policies() -> dict[str, Any]:
    params = load_house_3d_params()
    policies = deepcopy(load_interior_model()["room_policies"])
    for policy in policies.values():
        for field in ("floor", "ceiling"):
            override = policy[field].get("override_level_mm")
            policy[field]["level_mm"] = override if override is not None else _get_path(params, policy[field]["level_parameter"])
    return policies


def validate_model(module_id: str, model: dict[str, Any]) -> list[str]:
    """Validate editable geometry, units, provenance and relationships, not just files."""
    errors = []
    if model.get("schema_version") != 1 or model.get("module") != module_id:
        errors.append(f"{module_id}: invalid schema_version/module identity")
    expected_unit = "m" if module_id == "garden" else "mm"
    if model.get("units", {}).get("geometry") != expected_unit:
        errors.append(f"{module_id}: units.geometry must be {expected_unit}")
    records = model.get("provenance", {}).get("records", {})
    if not records:
        errors.append(f"{module_id}: provenance.records is required")
    for key, record in records.items():
        if not isinstance(record, dict) or record.get("type") not in PROVENANCE_TYPES or not record.get("source_id"):
            errors.append(f"{module_id}: invalid provenance record {key}")

    def walk(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                item_path = f"{path}.{key}"
                if key in {"bbox_mm", "bbox_m"} and item is not None:
                    if not (isinstance(item, list) and len(item) == 2 and
                            all(isinstance(v, list) and len(v) == 3 and all(_numeric(n) for n in v) for v in item) and
                            all(item[0][i] < item[1][i] for i in range(3))):
                        errors.append(f"{item_path}: expected increasing finite 3D bbox")
                if key == "core_opening_bbox_mm":
                    if not (isinstance(item, list) and len(item) == 4 and all(_numeric(n) for n in item)
                            and item[0] < item[2] and item[1] < item[3]):
                        errors.append(f"{item_path}: invalid opening bbox")
                if key in {"nominal_width_mm", "nominal_height_mm", "floor_thickness_mm", "slab_thickness_mm",
                           "finished_ceiling_height_mm", "external_insulation_mm"} and not (_numeric(item) and item > 0):
                    errors.append(f"{item_path}: expected positive finite dimension")
                if isinstance(item, float) and not math.isfinite(item):
                    errors.append(f"{item_path}: non-finite number")
                if key == "provenance" and isinstance(item, dict) and "type" in item:
                    if item.get("type") not in PROVENANCE_TYPES or not item.get("source_id"):
                        errors.append(f"{item_path}: invalid provenance")
                if key == "provenance":
                    continue
                if key.endswith("_mm") and item is not None and not isinstance(item, (dict, list)) and not _numeric(item):
                    errors.append(f"{item_path}: expected finite millimetres, not text or boolean")
                walk(item, item_path)
        elif isinstance(value, list):
            identifiers = [item["id"] for item in value if isinstance(item, dict) and "id" in item]
            if len(identifiers) != len(set(identifiers)):
                errors.append(f"{path}: duplicate IDs")
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
    walk(model, module_id)
    for palette_name in ("render_materials", "cad_render_materials", "palette"):
        for name, color in model.get(palette_name, {}).items():
            if not (isinstance(color, list) and len(color) == 4 and all(_numeric(n) and 0 <= n <= 1 for n in color)):
                errors.append(f"{module_id}.{palette_name}.{name}: RGBA must have four values in [0,1]")
    if module_id == "house_3d":
        for key, rule in model.get("derived_parameters", {}).items():
            if not isinstance(rule, dict) or rule.get("unit") != "mm":
                errors.append(f"house_3d.derived_parameters.{key}: unit must be mm")
        try:
            params = resolve_parameters(model)
            if params["finished_floor_level_mm"] != 0:
                errors.append("house_3d: finished_floor_level_mm must remain the local datum 0")
            for key in ("house_masonry_courses_to_parapet", "garage_masonry_courses_to_parapet"):
                if not isinstance(params[key], int) or isinstance(params[key], bool) or params[key] <= 0:
                    errors.append(f"house_3d.{key}: expected positive integer")
            if params["finished_ceiling_height_mm"] > params["wall_top_mm"]:
                errors.append("house_3d: ceiling cannot exceed structural wall top")
            if params["parapet_top_mm"] <= params["wall_top_mm"] + params["slab_thickness_mm"]:
                errors.append("house_3d: parapet must be above slab")
        except (KeyError, ValueError, TypeError, SyntaxError, ZeroDivisionError) as exc:
            errors.append(f"house_3d: invalid derived parameters: {exc}")
    if module_id == "house_2d":
        rooms = {room["number"] for room in model["source_data"]["rooms"]}
        for window in model["windows"]:
            if window["room_number"] not in rooms:
                errors.append(f"house_2d.{window['id']}: unknown room")
            if not (all(_numeric(window.get(k)) for k in ("sill_mm", "nominal_height_mm", "top_mm")) and
                    math.isclose(window["sill_mm"] + window["nominal_height_mm"], window["top_mm"], abs_tol=0.001)):
                errors.append(f"house_2d.{window['id']}: sill + height differs from top")
        door_ids = {door["id"] for door in model["source_data"]["doors"]}
        if set(model.get("opening_policies", {})) != door_ids:
            errors.append("house_2d: opening_policies must cover all doors")
    return errors


def _references(value, field):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == field:
                yield item
            yield from _references(item, field)
    elif isinstance(value, list):
        for item in value:
            yield from _references(item, field)


def validate_sources(manifest: dict, root: Path = ROOT) -> list[str]:
    errors = []
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), dict):
        return ["sources: expected schema_version 1 and sources mapping"]
    for source_id, source in manifest["sources"].items():
        availability = source.get("availability")
        if availability not in {"repository", "external", "unavailable"}:
            errors.append(f"sources.{source_id}: invalid availability")
        if source.get("status") not in PROVENANCE_TYPES:
            errors.append(f"sources.{source_id}: invalid status")
        if source.get("kind") == "file" and availability in {"repository", "external"}:
            digest = source.get("sha256", "")
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                errors.append(f"sources.{source_id}: SHA-256 required for available file")
        if availability == "repository":
            path = (root / source.get("path", "")).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f"sources.{source_id}: missing or unsafe repository path")
            elif source.get("sha256") and hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                errors.append(f"sources.{source_id}: SHA-256 mismatch")
    return errors


def validation_report() -> dict[str, Any]:
    """Public report contains uncertainty explicitly; unresolved decisions are not errors."""
    errors = []
    models = {}
    for module_id in MODULE_FILES:
        try:
            models[module_id] = load_module_model(module_id)
            errors.extend(validate_model(module_id, models[module_id]))
        except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as exc:
            errors.append(f"{module_id}: {exc}")
    try:
        manifest = load_yaml(ROOT / "sources" / "manifest.yaml")
        errors.extend(validate_sources(manifest))
        source_ids = set(manifest["sources"])
        for module_id, model in models.items():
            refs = list(_references(model, "source_id"))
            refs.extend(_references(model, "product_dimension_source_id"))
            module_manifest = load_yaml(MODULE_FILES[module_id].parent / "module.yaml")
            refs.extend(item.get("source_id") if isinstance(item, dict) else None for item in module_manifest.get("inputs", []))
            aliases = model.get("provenance", {}).get("legacy_source_aliases", {})
            refs.extend(aliases.values())
            for ref in set(refs):
                ref = aliases.get(ref, ref)
                if ref not in source_ids:
                    errors.append(f"{module_id}: unknown source reference {ref!r}")
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as exc:
        errors.append(f"sources: {exc}")
    decisions = load_decision_register()["decisions"]
    decision_ids = {decision["id"] for decision in decisions}
    if len(decision_ids) != len(decisions):
        errors.append("decisions: duplicate IDs")
    for decision in decisions:
        if decision.get("status") not in DECISION_STATES or not decision.get("required_evidence"):
            errors.append(f"decisions.{decision['id']}: invalid state or missing evidence")
    for module_id, model in models.items():
        for ref in _references(model, "decision_id"):
            if ref not in decision_ids:
                errors.append(f"{module_id}: unknown decision reference {ref!r}")
    if "interior" in models and "house_3d" in models and "house_2d" in models:
        try:
            params = resolve_parameters(models["house_3d"])
            policies = models["interior"]["room_policies"]
            room_ids = {room["id"] for room in models["house_2d"]["source_data"]["rooms"]}
            if set(policies) != room_ids:
                errors.append("interior: room_policies must cover every room")
            for room_id, policy in policies.items():
                levels = {}
                for name in ("floor", "ceiling"):
                    parameter_level = _get_path(params, policy[name]["level_parameter"])
                    if not _numeric(parameter_level):
                        errors.append(f"interior.{room_id}.{name}: invalid level reference")
                    override = policy[name].get("override_level_mm")
                    if override is not None and not _numeric(override):
                        errors.append(f"interior.{room_id}.{name}: override must be finite millimetres or null")
                    levels[name] = parameter_level if override is None else override
                if all(_numeric(level) for level in levels.values()):
                    if levels["floor"] >= levels["ceiling"]:
                        errors.append(f"interior.{room_id}: ceiling must be above floor")
                    if levels["ceiling"] > params["wall_top_mm"]:
                        errors.append(f"interior.{room_id}: ceiling cannot exceed structural wall top")
                for name, item in policy.items():
                    if isinstance(item, dict) and item.get("decision_id") and item["decision_id"] not in decision_ids:
                        errors.append(f"interior.{room_id}.{name}: unknown decision")
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"interior: invalid policy {exc}")
    warnings = [{"id": d["id"], "status": d["status"], "message": d["title"],
                 "affected_ids": d.get("affected_ids", [])} for d in decisions if d["status"] != "resolved"]
    # Closing a decision is not evidence of a surveyed, approved construction design.
    # This validator reports consistency only; fabrication acceptance stays manual.
    return {"schema_version": 1, "ok": not errors, "errors": errors,
            "warnings": warnings,
            "decision_register_complete": not warnings,
            "manual_acceptance_required": True,
            "ready_for_fabrication": False}
