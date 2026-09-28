#!/usr/bin/env python3
"""Walidacja manifestu modułowego i planowanie zależności."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Brak PyYAML. Uruchom: python -m pip install PyYAML") from exc

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = ROOT / "project.yaml"
ALLOWED = {"legacy", "hybrid", "declarative"}

def load_yaml(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def dependency_plan(cfg, target):
    modules = cfg["modules"]
    if target not in modules:
        raise KeyError(target)
    result, visiting, visited = [], set(), set()
    def visit(mid):
        if mid in visited:
            return
        if mid in visiting:
            raise ValueError(f"Cykl zależności przy module {mid}")
        visiting.add(mid)
        for dep in modules[mid].get("depends_on", []):
            if dep not in modules:
                raise ValueError(f"Nieznana zależność {dep} modułu {mid}")
            visit(dep)
        visiting.remove(mid)
        visited.add(mid)
        result.append(mid)
    visit(target)
    return result

def validate(cfg):
    errors = []
    modules = cfg.get("modules", {})
    for mid, meta in modules.items():
        module_dir = ROOT / meta["path"]
        manifest_path = module_dir / "module.yaml"
        if not manifest_path.exists():
            errors.append(f"{mid}: brak {manifest_path.relative_to(ROOT)}")
            continue
        manifest = load_yaml(manifest_path) or {}
        if manifest.get("id") != mid:
            errors.append(f"{mid}: niezgodne id w module.yaml")
        if list(manifest.get("depends_on", [])) != list(meta.get("depends_on", [])):
            errors.append(f"{mid}: depends_on różni się od project.yaml")
        status = manifest.get("migration", {}).get("status")
        if status not in ALLOWED or status != meta.get("migration"):
            errors.append(f"{mid}: niespójny migration.status={status!r}")
        if status == "declarative":
            declarative_file = manifest.get("declarative", {}).get("file")
            if not declarative_file:
                errors.append(f"{mid}: declarative module wymaga declarative.file")
            elif not (ROOT / declarative_file).exists():
                errors.append(f"{mid}: brak declarative.file: {declarative_file}")
            if manifest.get("legacy", {}).get("authoritative", []):
                errors.append(f"{mid}: declarative module nie może mieć legacy.authoritative")
        for rel in manifest.get("legacy", {}).get("authoritative", []):
            if not (ROOT / rel).exists():
                errors.append(f"{mid}: brak legacy authoritative: {rel}")
        for rel in manifest.get("execution", {}).get("legacy_entrypoints", []):
            if not (ROOT / rel).exists():
                errors.append(f"{mid}: brak entrypointu: {rel}")
    for mid in modules:
        try:
            dependency_plan(cfg, mid)
        except ValueError as exc:
            errors.append(str(exc))
    order = cfg.get("workflow", {}).get("default_order", [])
    if len(order) != len(set(order)) or set(order) != set(modules):
        errors.append("workflow.default_order musi zawierać każdy moduł dokładnie raz")
    return errors

def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("validate")
    sp.add_parser("status")
    pp = sp.add_parser("plan")
    pp.add_argument("module")
    args = p.parse_args()
    cfg = load_yaml(PROJECT_FILE)
    if args.cmd == "validate":
        errors = validate(cfg)
        if errors:
            print("Walidacja NIEUDANA:")
            for err in errors:
                print(" -", err)
            raise SystemExit(1)
        print(f"OK: {len(cfg['modules'])} modułów i zależności są spójne.")
        return
    if args.cmd == "status":
        for mid, meta in cfg["modules"].items():
            m = load_yaml(ROOT / meta["path"] / "module.yaml")
            print(f"{mid:10} {m['migration']['status']:11} {m['title']}")
        return
    try:
        print(" -> ".join(dependency_plan(cfg, args.module)))
    except KeyError:
        print(f"Nieznany moduł: {args.module}", file=sys.stderr)
        raise SystemExit(2)

if __name__ == "__main__":
    main()
