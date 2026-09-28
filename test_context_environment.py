"""Regressions for repeated terrain builds (no Git history or network required)."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import uaktualnij_teren_i_otoczenie as updater


def mesh_components(part):
    """Use face connectivity, independent of cylinder vertex counts/order."""
    parents = list(range(len(part['positions_m'])))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for face in part['faces']:
        for vertex in face[1:]:
            parents[find(vertex)] = find(face[0])
    groups = {}
    for i in range(len(parents)):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda group: group[0])


class ContextEnvironmentRegression(unittest.TestCase):
    def test_repeated_build_preserves_sources_and_tree_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(updater.ROOT / 'geoportal_teren.json', root / 'geoportal_teren.json')
            # Keep a sentinel house part to check that only context geometry changes.
            house = {'name': 'HOUSE_SENTINEL', 'positions_m': [[1, 2, 3]], 'faces': []}
            (root / 'scena_modelu.json').write_text(json.dumps({'parts': [house]}))
            source_path = updater.ROOT / 'modules' / '02_terrain' / 'model.yaml'
            source_bytes = source_path.read_bytes()
            source = updater.load_terrain_model()['context_geometry']
            with patch.object(updater, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                updater.main()
                first = {name: (root / name).read_bytes()
                         for name in ('geoportal_teren.json', 'scena_modelu.json')}
                updater.main()
            for name, expected in first.items():
                self.assertEqual((root / name).read_bytes(), expected, name)
            self.assertEqual(source_path.read_bytes(), source_bytes)

            terrain = json.loads(first['geoportal_teren.json'])
            scene = json.loads(first['scena_modelu.json'])
            parts = {p['name']: p for p in terrain['parts']}
            trunks = parts['GEO_DRZEWA_PNIE']
            components = mesh_components(trunks)
            self.assertEqual(len(components), 180)
            positions = np.asarray(trunks['positions_m'])
            for indices, anchor in zip(components, source['tree_anchors_m']):
                vertices = positions[indices]
                actual = [*(vertices[:, :2].min(axis=0) + vertices[:, :2].max(axis=0)) / 2,
                          vertices[:, 2].min()]
                np.testing.assert_allclose(actual, anchor, atol=1e-6, rtol=0)
            # Tree triangles stay at or below the pre-regression baseline.
            tree_triangles = sum(len(p['faces']) for p in terrain['parts']
                                 if p['name'].startswith('GEO_DRZEWA_'))
            self.assertLessEqual(tree_triangles, 18720)
            self.assertEqual(terrain['stats']['trees'], 180)
            self.assertEqual(terrain['stats']['context_buildings'], 19)
            self.assertEqual(scene['parts'][0], house)
            self.assertEqual(scene['geo_alignment'], terrain['alignment'])
            self.assertEqual(scene['geo_validation'], terrain['validation'])
            validation = terrain['validation']
            self.assertNotIn('nmt_at_model_center_m', validation)
            self.assertEqual(validation['nmt_sample_epsg2180'],
                             terrain['alignment']['geo_context_center_epsg2180'])
            self.assertEqual(validation['nmt_at_fetch_center_m'], 253.08)
            self.assertAlmostEqual(validation['nmt_fetch_center_relative_to_model_zero_m'],
                                   253.08 - terrain['alignment']['model_zero_elevation_m'])
            self.assertEqual(validation['house_alignment_source'], 'PZT_survey_grid_project')
            np.testing.assert_allclose(validation['calibrated_house_centroid_epsg2180'],
                                       [506159.240, 331679.519], atol=0.002, rtol=0)

    def test_rejects_incompatible_source_grid(self):
        terrain = json.loads((updater.ROOT / 'geoportal_teren.json').read_text())
        nmt = next(p for p in terrain['parts'] if p['name'] == 'GEO_NMT_rzeczywisty')
        nmt['positions_m'][0][0] += 1
        with self.assertRaisesRegex(ValueError, 'Geometria źródłowa'):
            updater.load_context_source(terrain)


if __name__ == '__main__':
    unittest.main()
