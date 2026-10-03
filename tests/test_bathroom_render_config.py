"""Rendering must consume canonical fixtures, preserve their placement and declare finishes."""
import unittest

import numpy as np

from bathroom_geometry import build_bathroom
from project_config import load_interior_model
from scripts.render_bathroom import DEFAULT_CONFIG, load_configuration, select_parts


class BathroomRenderContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        interior = load_interior_model()
        cls.config = load_configuration(DEFAULT_CONFIG)
        cls.bathroom = interior['bathroom']
        cls.parts = []

        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append({'name': name, 'category': category, 'material': material,
                              'source_id': source_id, 'positions_m': mesh.vertices.tolist(),
                              'faces': mesh.faces.tolist(), **extras})

        build_bathroom(cls.bathroom, collect, finishes=interior['bathroom_finishes'])
        cls.scene = {'units': 'm', 'up_axis': 'Z', 'coordinate_frame': 'building_local', 'parts': cls.parts}

    def test_renderer_preserves_every_fixture_and_finish_and_excludes_blocks(self):
        selected = select_parts(self.scene, self.config)
        expected = {p['name'] for p in self.parts if p.get('interior_layer') == 'selected'}
        self.assertEqual({p['name'] for p, _, _ in selected}, expected)
        frame = self.config['frame']
        origin = np.asarray(frame['origin_mm']) / 1000
        basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
        self.assertEqual(frame, {k: self.bathroom['frame'][k] for k in frame})
        for part, vertices, faces in selected:
            restored = np.asarray(vertices) @ basis.T + origin
            np.testing.assert_allclose(restored, part['positions_m'], atol=1e-12)
            self.assertEqual(faces, part['faces'])
            self.assertIn(part['material'], self.config['materials'], part['name'])

    def test_renderer_refuses_unfinished_or_wrong_coordinate_scenes(self):
        scene = {**self.scene, 'parts': [p for p in self.parts if not p.get('bathroom_finish')]}
        with self.assertRaisesRegex(ValueError, 'finish geometry missing'):
            select_parts(scene, self.config)
        with self.assertRaisesRegex(ValueError, 'metre/Z-up'):
            select_parts({**self.scene, 'up_axis': 'Y'}, self.config)
        with self.assertRaisesRegex(ValueError, 'building_local'):
            select_parts({**self.scene, 'coordinate_frame': 'georeferenced'}, self.config)

    def test_camera_is_inside_room_at_an_eye_level_and_materials_are_conceptual(self):
        room = load_interior_model()['bathroom_finishes']['room_reference']
        for name, camera in self.config['cameras'].items():
            x, y, z = camera['position_mm']
            self.assertTrue(0 < x < room['width_mm'], name)
            self.assertTrue(0 < y < room['depth_mm'], name)
            self.assertTrue(1200 <= z <= 1800, name)
            self.assertGreaterEqual(camera['lens_mm'], 18, name)
        self.assertEqual(self.config['provenance']['type'], 'assumed')
        self.assertIn('not_product_selection', self.config['status'])


if __name__ == '__main__':
    unittest.main()
