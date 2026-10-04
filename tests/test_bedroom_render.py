"""Bedroom render optics preserve the canonical room and authored mural placement."""
import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np
import yaml

from bedroom_geometry import build_bedroom
from scripts.render_bathroom import (
    DEFAULT_CONFIG, ROOT, create_material, image_texture_path, load_configuration,
    select_parts, shader_coordinate_transform, to_canonical_m, to_local_m,
)


BEDROOM_CONFIG = DEFAULT_CONFIG.with_name('bedroom-render.yaml')


class BedroomRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_configuration(BEDROOM_CONFIG)
        cls.layout = yaml.safe_load(BEDROOM_CONFIG.with_name('bedroom.yaml').read_text(encoding='utf-8'))
        cls.parts = []

        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append({'name': name, 'category': category, 'material': material,
                              'source_id': source_id, 'positions_m': mesh.vertices.tolist(),
                              'faces': mesh.faces.tolist(), **extras})

        build_bedroom(cls.layout, collect)
        cls.scene = {'units': 'm', 'up_axis': 'Z', 'coordinate_frame': 'building_local', 'parts': cls.parts}

    def test_room_selection_keeps_all_bedroom_parts_without_moving_them(self):
        before = copy.deepcopy(self.scene)
        selected = select_parts(self.scene, self.config, scope='room')
        self.assertEqual({part['name'] for part, _, _ in selected}, {part['name'] for part in self.parts})
        self.assertEqual(self.scene, before)
        self.assertGreater(len(selected), 20)
        self.assertFalse(any(part.get('bathroom_fixture') for part, _, _ in selected))
        for part, vertices, faces in selected:
            self.assertEqual(faces, part['faces'])
            self.assertIn(part['material'], self.config['materials'])
            np.testing.assert_allclose([to_canonical_m(point, self.config['frame']) for point in vertices],
                                       part['positions_m'], atol=1e-12)

    def test_missing_room_finishes_are_detected(self):
        scene = {**self.scene, 'parts': [part for part in self.parts if not part.get('interior_finish')]}
        with self.assertRaisesRegex(ValueError, 'finish geometry missing'):
            select_parts(scene, self.config, scope='room')

    def test_house_profile_preserves_mural_and_fabric_coordinates(self):
        house = load_configuration(DEFAULT_CONFIG, scope='house')
        expected = shader_coordinate_transform(house['frame'], self.config['frame'])
        image_spec = house['materials']['bedroom_mural']['image_texture']
        self.assertEqual(image_spec['coordinate_transform'], expected)
        for key in self.config['surface_shaders']:
            self.assertEqual(house['surface_shaders'][key]['coordinate_transform'], expected)
        # Opposing bedroom and bathroom frames must neither mirror nor rotate the mural.
        for local_point in ([.015, 3.6208, 1.45], [3.4621, 3.6208, 2.835]):
            canonical = to_canonical_m(local_point, self.config['frame'])
            render_point = np.array(to_local_m(canonical, house['frame']))
            mapped = np.array(expected['rows']) @ render_point + expected['offset_m']
            np.testing.assert_allclose(mapped, local_point, atol=1e-12)
        inverse = load_configuration(BEDROOM_CONFIG, scope='house')
        self.assertIn('bathroom_tile_marble', inverse['materials'])
        self.assertIn('small_bathroom_gray_stone', inverse['marble_shaders'])

    def test_mural_matches_geometry_and_is_a_real_project_asset(self):
        spec = self.config['materials']['bedroom_mural']['image_texture']
        mural = next(part for part in self.parts if part.get('interior_fixture') == 'FIN_BEDROOM_MURAL')
        local = np.array([to_local_m(point, self.config['frame']) for point in mural['positions_m']]) * 1000
        np.testing.assert_allclose(local.min(axis=0), spec['origin_mm'], atol=1e-8)
        np.testing.assert_allclose((local.max(axis=0)-local.min(axis=0))[[0, 2]], spec['size_mm'], atol=1e-8)
        self.assertEqual(spec['axes'], [[1, 0, 0], [0, 0, 1]])
        self.assertTrue(image_texture_path(spec).is_file())
        for path in ('../../outside.jpg', '/tmp/outside.png', 'assets/not-an-image.py'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                image_texture_path({'path': path})

    @unittest.skipUnless(importlib.util.find_spec('bpy'), 'Optional Blender runtime not installed')
    def test_cycles_artwork_is_packed_and_textile_nodes_build(self):
        import bpy
        for key in ('bedroom_mural', 'bedroom_headboard', 'bedroom_bedding', 'bedroom_pillow'):
            material = create_material(bpy, key, self.config)
            self.assertIsNotNone(material.node_tree.nodes.get('Principled BSDF'))
            if key == 'bedroom_mural':
                image = next(node.image for node in material.node_tree.nodes if node.type == 'TEX_IMAGE')
                self.assertIsNotNone(image.packed_file)
                self.assertGreater(image.size[0], 100)


if __name__ == '__main__':
    unittest.main()
