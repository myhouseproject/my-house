"""Configuration regressions: reject unsafe/invalid geometry and preserve uncertainty."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import project_config as config


class ConfigurationValidationTests(unittest.TestCase):
    def test_every_module_geometry_units_and_provenance_validate(self):
        for module_id in config.MODULE_FILES:
            with self.subTest(module=module_id):
                self.assertEqual(config.validate_model(module_id, config.load_module_model(module_id)), [])

    def test_ceiling_edit_does_not_move_shell_or_garage(self):
        model = config.load_module_model("house_3d")
        before = config.resolve_parameters(model)
        model["parameters"]["finished_ceiling_height_mm"] = 2900
        after = config.resolve_parameters(model)
        self.assertEqual(after["plenum_space_mm"], 200)
        self.assertEqual(after["ceiling_level_mm"], 2900)
        for key in ("wall_top_mm", "parapet_top_mm", "garage_floor_offset_mm", "floor_structural_base_mm"):
            self.assertEqual(before[key], after[key], key)

    def test_derived_parameters_reject_cycles_literals_and_code(self):
        baseline = config.load_module_model("house_3d")
        for change in ("cycle", "literal", "code"):
            model = deepcopy(baseline)
            if change == "cycle":
                model["derived_parameters"]["ceiling_level_mm"]["expression"] = "plenum_space_mm"
            elif change == "literal":
                model["parameters"]["ceiling_level_mm"] = 2850
            else:
                model["derived_parameters"]["ceiling_level_mm"]["expression"] = "__import__('os').system('echo unsafe')"
            with self.subTest(change=change), self.assertRaises(ValueError):
                config.resolve_parameters(model)

    def test_invalid_geometry_and_units_are_not_green(self):
        model = config.load_module_model("house_2d")
        model["windows"][0]["nominal_width_mm"] = -100
        model["windows"][1]["core_opening_bbox_mm"] = [0, 0, 0, 300]
        model["windows"][2]["room_number"] = 999
        model["units"]["geometry"] = "inches"
        errors = config.validate_model("house_2d", model)
        for text in ("positive finite", "invalid opening bbox", "unknown room", "units.geometry"):
            self.assertTrue(any(text in error for error in errors), (text, errors))

    def test_invalid_provenance_duplicate_id_and_top_level_are_detected(self):
        model = config.load_module_model("house_2d")
        model["provenance"]["records"]["module"]["type"] = "certain"
        model["windows"][1]["id"] = model["windows"][0]["id"]
        model["windows"][0]["top_mm"] += 100
        errors = config.validate_model("house_2d", model)
        for text in ("invalid provenance", "duplicate IDs", "sill + height"):
            self.assertTrue(any(text in error for error in errors), errors)

    def test_external_source_does_not_need_public_copy_but_requires_hash(self):
        source = {"kind": "file", "availability": "external", "status": "project",
                  "sha256": "a" * 64, "original_name": "private.pdf"}
        manifest = {"schema_version": 1, "sources": {"private": source}}
        self.assertEqual(config.validate_sources(manifest), [])
        source.pop("sha256")
        self.assertTrue(config.validate_sources(manifest))

    def test_repository_source_hash_and_path_are_checked(self):
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("verified", encoding="utf-8")
            source = {"kind": "file", "availability": "repository", "status": "project",
                      "path": "evidence.txt", "sha256": hashlib.sha256(b"verified").hexdigest()}
            manifest = {"schema_version": 1, "sources": {"source": source}}
            self.assertEqual(config.validate_sources(manifest, root), [])
            (root / "evidence.txt").write_text("changed", encoding="utf-8")
            self.assertIn("SHA-256 mismatch", config.validate_sources(manifest, root)[0])
            source["path"] = "../outside.pdf"
            self.assertIn("unsafe", config.validate_sources(manifest, root)[0])

    def test_room_override_is_local_and_does_not_claim_measurement(self):
        model = config.load_interior_model()
        model["room_policies"]["R10"]["ceiling"]["override_level_mm"] = 2900
        with patch.object(config, "load_interior_model", return_value=model):
            policies = config.load_room_policies()
        self.assertEqual(policies["R10"]["ceiling"]["level_mm"], 2900)
        self.assertEqual(policies["R11"]["ceiling"]["level_mm"], 2850)
        self.assertEqual(policies["R10"]["ceiling"]["status"], "assumed")
        self.assertIsNone(policies["R10"]["finished_faces"]["wall_finish_thickness_mm"])

    def test_source_furniture_height_and_physical_conflicts_are_preserved(self):
        model = config.load_interior_model()
        tall = next(block for block in model["project"]["layers"]["blocks"] if block["id"] == "HOL_WARDROBE")
        self.assertEqual(tall["bbox_mm"][1][2], 2900)
        self.assertEqual(config.load_house_3d_params()["finished_ceiling_height_mm"], 2850)
        decisions = {d["id"]: d for d in config.load_decision_register()["decisions"]}
        self.assertEqual(decisions["D-CEILING"]["status"], "pending_measurement")
        self.assertEqual(decisions["D-ART-DR11"]["status"], "pending_decision")
        self.assertTrue(all(not window["provenance"]["installation_verified"] for window in config.load_house_2d_model()["windows"]))

    def test_room_levels_reject_impossible_clear_height_and_structural_ceiling(self):
        models = {module: config.load_module_model(module) for module in config.MODULE_FILES}
        models["interior"]["room_policies"]["R10"]["ceiling"]["override_level_mm"] = 3300
        models["interior"]["room_policies"]["R13"]["floor"]["override_level_mm"] = 3000
        with patch.object(config, "load_module_model", side_effect=lambda module: models[module]):
            report = config.validation_report()
        self.assertFalse(report["ok"])
        self.assertIn("interior.R10: ceiling cannot exceed structural wall top", report["errors"])
        self.assertIn("interior.R13: ceiling must be above floor", report["errors"])

    def test_closing_decisions_cannot_certify_fabrication(self):
        decisions = config.load_decision_register()
        for decision in decisions["decisions"]:
            decision["status"] = "resolved"
        with patch.object(config, "load_decision_register", return_value=decisions):
            report = config.validation_report()
        self.assertTrue(report["decision_register_complete"])
        self.assertTrue(report["manual_acceptance_required"])
        self.assertFalse(report["ready_for_fabrication"])

    def test_caches_prefer_explicit_staged_input(self):
        with tempfile.TemporaryDirectory(dir=config.ROOT) as directory:
            root = Path(directory)
            self.assertEqual(config.cached_input_path(root, "map.json"), root / "data/map.json")
            (root / "map.json").write_text("{}")
            self.assertEqual(config.cached_input_path(root, "map.json"), root / "map.json")


if __name__ == "__main__":
    unittest.main()
