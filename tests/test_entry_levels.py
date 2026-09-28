"""Regression checks for the finished floor, entrance landing and declarative config."""
import json
from pathlib import Path
import unittest

import numpy as np

from project_config import load_house_3d_model, load_house_3d_params

ROOT = Path(__file__).resolve().parents[1]


class EntryLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_house_3d_model()
        cls.params = load_house_3d_params()
        cls.scene = json.loads((ROOT / "scena_modelu.json").read_text(encoding="utf-8"))
        cls.parts = {part["name"]: part for part in cls.scene["parts"]}

    def test_yaml_is_house_3d_source_of_truth(self):
        self.assertEqual(self.model["module"], "house_3d")
        self.assertEqual(self.model["schema_version"], 1)
        self.assertIn("provenance", self.model)
        legacy = json.loads((ROOT / "parametry_modelu.json").read_text(encoding="utf-8"))
        self.assertEqual(
            legacy,
            self.params,
            "parametry_modelu.json is only a generated compatibility snapshot; run scripts/sync_legacy_config.py",
        )

    def test_zero_is_finished_floor_and_as_built_base_is_29_cm_lower(self):
        self.assertEqual(self.params["finished_floor_level_mm"], 0)
        self.assertEqual(self.params["floor_thickness_mm"], 290)
        self.assertEqual(self.params["floor_structural_base_mm"], -290)
        floor = self.parts["PODLOGA_pakiet_stan_wykonany"]
        z = np.asarray(floor["positions_m"], dtype=float)[:, 2]
        self.assertAlmostEqual(float(z.max()), 0.0, places=6)
        self.assertAlmostEqual(float(z.min()), -0.29, places=6)

    def test_entrance_threshold_stays_at_zero_and_landing_is_29_cm_lower(self):
        door = self.parts["DR02_skrzydlo_ALTUS"]
        landing = self.parts["PODEST_WEJSCIOWY_BETON"]
        door_z = np.asarray(door["positions_m"], dtype=float)[:, 2]
        landing_z = np.asarray(landing["positions_m"], dtype=float)[:, 2]
        self.assertAlmostEqual(float(door_z.min()), 0.0, places=6)
        self.assertAlmostEqual(float(landing_z.max()), -0.29, places=6)
        self.assertAlmostEqual(float(door_z.min() - landing_z.max()), 0.29, places=6)
        self.assertEqual(landing["category"], "nawierzchnie")
        self.assertEqual(landing["step_geometry_status"], "pending")

    def test_project_nominal_entry_reference_is_kept_separate_from_as_built_value(self):
        landing = self.params["entrance_landing"]
        self.assertEqual(landing["top_z_mm"], -290)
        self.assertEqual(landing["project_reference_top_z_mm"], -300)
        self.assertIn("253,70", landing["note"])
        self.assertIn("254,00", landing["note"])


if __name__ == "__main__":
    unittest.main()
