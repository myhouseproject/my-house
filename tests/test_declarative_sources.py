"""Ensure legacy configuration files are generated snapshots of module YAMLs."""
import json
from pathlib import Path
import unittest

from project_config import (
    load_map_config,
    load_terrain_model,
    load_house_2d_model,
    load_house_3d_params,
    load_finishes_model,
    load_interior_model,
    load_garden_model,
)

ROOT = Path(__file__).resolve().parents[1]


class DeclarativeSourceTests(unittest.TestCase):
    def read_json(self, name):
        return json.loads((ROOT / name).read_text(encoding="utf-8"))

    def test_legacy_snapshots_match_declarative_sources(self):
        terrain = load_terrain_model()
        house = load_house_2d_model()
        finishes = load_finishes_model()
        interior = load_interior_model()
        expected = {
            "geoportal_georef.json": load_map_config(),
            "pzt_zagospodarowanie.json": terrain["site"],
            "context_geometry_source.json": terrain["context_geometry"],
            "dane_zrodlowe.json": house["source_data"],
            "obrys_dachu_z_pdf.json": house["roof"],
            "okna_projektowe.json": house["windows"],
            "stolarka_zewnetrzna.json": house["external_joinery"],
            "parametry_modelu.json": load_house_3d_params(),
            "elewacje_materialy.json": finishes["elevations"],
            "wnetrze_projekt.json": interior["project"],
        }
        for path, value in expected.items():
            with self.subTest(path=path):
                self.assertEqual(
                    self.read_json(path),
                    value,
                    f"{path} is a compatibility snapshot; run scripts/sync_legacy_config.py",
                )

    def test_all_modules_have_declarative_identity(self):
        project = __import__("yaml").safe_load((ROOT / "project.yaml").read_text(encoding="utf-8"))
        self.assertTrue(all(meta["migration"] == "declarative" for meta in project["modules"].values()))
        self.assertEqual(load_house_2d_model()["module"], "house_2d")
        self.assertEqual(load_terrain_model()["module"], "terrain")
        self.assertEqual(load_finishes_model()["module"], "finishes")
        self.assertEqual(load_interior_model()["module"], "interior")
        self.assertEqual(load_garden_model()["module"], "garden")
        self.assertIn("recipe", load_garden_model())
        self.assertIn("generator_recipe", load_interior_model())
        self.assertIn("generator_recipe", load_finishes_model())


if __name__ == "__main__":
    unittest.main()
