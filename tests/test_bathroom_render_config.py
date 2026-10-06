"""Rendering must consume canonical fixtures, preserve their placement and declare finishes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from bathroom_geometry import build_bathroom
from project_config import load_interior_model
from scripts.render_bathroom import (DEFAULT_CONFIG, apply_portal_camera, apply_portal_visibility,
                                    apply_tile_variant, camera_basis, load_camera_file, load_configuration,
                                    material_spec, select_parts)


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

    def test_product_tile_variant_maps_atlas_to_real_tile_grid(self):
        variant = apply_tile_variant(self.config, 'opoczno_calacatta_paonazzo')
        self.assertEqual(variant['active_tile_variant'], 'opoczno_calacatta_paonazzo')
        self.assertEqual(variant['active_tile_product']['manufacturer'], 'Opoczno')
        floor = next(part for part in self.parts if part['name'] == 'FIN_BATH_FLOOR_tiles')
        wall = next(part for part in self.parts if part['name'] == 'FIN_BATH_EAST_BACKSPLASH_tiles')
        floor_spec = material_spec(floor, variant)
        wall_spec = material_spec(wall, variant)
        self.assertNotIn('marble', floor_spec)
        self.assertNotIn('tile_image_atlas', floor_spec)
        self.assertEqual(floor_spec['image_texture']['axes'], [[1, 0, 0], [0, 1, 0]])
        self.assertEqual(wall_spec['image_texture']['axes'], [[0, 1, 0], [0, 0, 1]])
        self.assertEqual(floor_spec['image_texture']['size_mm'], [4800.0, 4800.0])
        self.assertEqual(wall_spec['image_texture']['size_mm'], [4800.0, 2400.0])
        self.assertEqual(floor_spec['image_texture']['origin_mm'][:2],
                         [float(value) for value in floor['finish_grid_origin_uv_mm']])
        with self.assertRaisesRegex(ValueError, 'Unknown bathroom tile variant'):
            apply_tile_variant(self.config, 'not-a-product')

    def test_product_tile_variant_supports_formats(self):
        v120 = apply_tile_variant(self.config, 'opoczno_calacatta_marble', '120x120')
        self.assertEqual(v120['active_tile_format'], '120x120')
        floor = next(part for part in self.parts if part['name'] == 'FIN_BATH_FLOOR_tiles')
        spec120 = material_spec(floor, v120)
        self.assertEqual(spec120['image_texture']['size_mm'], [4800.0, 4800.0])

        v280 = apply_tile_variant(self.config, 'opoczno_calacatta_marble', '120x280')
        self.assertEqual(v280['active_tile_format'], '120x280')
        spec280 = material_spec(floor, v280)
        self.assertEqual(spec280['image_texture']['size_mm'], [4800.0, 11200.0])

    def portal_camera(self, **changes):
        camera = {'schema_version': 1, 'kind': 'dom-render-camera', 'coordinate_frame': 'building_local',
                  'units': 'm', 'up_axis': 'Z', 'projection': 'perspective',
                  'eye': [26.4774, 6.2842, 1.55], 'target': [26.5374, 2.8892, 1.30],
                  'up': [0, 0, 1], 'vertical_fov_degrees': 60,
                  'aspect_ratio': 0.6, 'resolution': [1200, 2000]}
        camera.update(changes)
        return camera

    def read_camera(self, camera):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'camera.json'
            path.write_text(json.dumps(camera), encoding='utf-8')
            return load_camera_file(path, self.scene)

    def test_portal_camera_round_trip_preserves_view_and_config(self):
        camera = self.read_camera(self.portal_camera())
        before = copy.deepcopy(self.config)
        config = apply_portal_camera(self.config, camera)
        spec = config['cameras']['portal']
        np.testing.assert_allclose(spec['position_mm'], self.config['cameras']['entrance']['position_mm'])
        np.testing.assert_allclose(spec['target_mm'], self.config['cameras']['entrance']['target_mm'])
        self.assertEqual(spec['vertical_fov_degrees'], 60)
        self.assertEqual(spec['up'], [0, 0, 1])
        self.assertEqual(config['render']['final']['resolution'], [1200, 2000])
        self.assertEqual(self.config, before)
        basis = np.asarray(camera_basis(camera['eye'], camera['target'], camera['up'])).T
        np.testing.assert_allclose(basis.T @ basis, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(basis), 1)
        np.testing.assert_allclose(basis[:, 1] @ np.asarray(camera['up']),
                                   np.linalg.norm(np.cross(basis[:, 2], camera['up'])))

    def test_portal_orthographic_top_view_has_non_degenerate_orientation(self):
        camera = self.read_camera(self.portal_camera(projection='orthographic', eye=[26, 4, 8],
                                  target=[26, 4, 0], up=[0, 1, 0], orthographic_height_m=5))
        config = apply_portal_camera(self.config, camera)
        self.assertEqual(config['cameras']['portal']['orthographic_height_m'], 5)
        np.testing.assert_allclose(camera_basis(camera['eye'], camera['target'], camera['up']),
                                   np.eye(3), atol=1e-12)

    def test_invalid_camera_input_is_rejected_before_blender(self):
        invalid = [
            {'coordinate_frame': 'georeferenced'}, {'units': 'mm'}, {'up_axis': 'Y'},
            {'schema_version': True}, {'eye': [float('nan'), 1, 2]}, {'eye': [float('inf'), 1, 2]},
            {'eye': [True, 1, 2]}, {'eye': [1e9, 1, 2]}, {'up': [0, 0, 0]},
            {'target': self.portal_camera()['eye']}, {'projection': 'panoramic'},
            {'vertical_fov_degrees': 180}, {'resolution': [9000, 2000]},
            {'resolution': [True, 2000]}, {'aspect_ratio': 1},
            {'projection': 'orthographic', 'orthographic_height_m': -1},
            {'visible_part_names': ['not-in-this-release']},
            {'visible_part_names': [self.parts[0]['name'], self.parts[0]['name']]},
            {'section_height_m': float('nan')}, {'clip_bounds_m': [[0, 0, 1], [1, 1, 0]]},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.read_camera(self.portal_camera(**changes))
        with self.assertRaisesRegex(ValueError, 'parallel'):
            self.read_camera(self.portal_camera(eye=[26, 4, 2], target=[26, 4, 1], up=[0, 0, 1]))

    def test_house_scope_keeps_full_geometry_and_canonical_materials(self):
        triangle = [[12, 6, 0], [14, 6, 0], [12, 9, 0]]
        part = {'name': 'OTHER_ROOM', 'category': 'podlogi', 'material': 'other_material',
                'positions_m': triangle, 'faces': [[0, 1, 2]], 'color': [0.3, 0.4, 0.5, 1],
                'pbr': {'roughness': 0.31, 'metallic': 0.7}}
        scene = {**self.scene, 'parts': self.parts + [part, {**part, 'name': 'SITE', 'category': 'ortofoto'}]}
        selected = select_parts(scene, self.config, 'house')
        actual = next(item for item in selected if item[0]['name'] == 'OTHER_ROOM')
        frame = self.config['frame']
        basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
        np.testing.assert_allclose(np.asarray(actual[1]) @ basis.T + np.asarray(frame['origin_mm'])/1000,
                                   triangle, atol=1e-12)
        self.assertEqual(actual[2], part['faces'])
        self.assertNotIn('SITE', [item[0]['name'] for item in selected])
        spec = material_spec(part, self.config)
        self.assertEqual(spec['color_srgb'], [0.3, 0.4, 0.5])
        self.assertEqual(spec['roughness'], 0.31)
        self.assertEqual(spec['metallic'], 0.7)

    def test_portal_section_and_visibility_do_not_modify_canonical_geometry(self):
        selected = select_parts(self.scene, self.config)
        before = copy.deepcopy(selected)
        name = next(p['name'] for p, vertices, _ in selected
                    if min(v[2] for v in vertices) < 1.2 < max(v[2] for v in vertices))
        camera = self.read_camera(self.portal_camera(visible_part_names=[name], section_height_m=1.2,
                                  clip_bounds_m=[[25, 2, -1], [28, 7, 3]]))
        clipped = apply_portal_visibility(selected, camera, self.config)
        self.assertEqual({p['name'] for p, _, _ in clipped}, {name})
        self.assertTrue(all(point[2] <= 1.2 + 1e-12 for _, vertices, _ in clipped for point in vertices))
        self.assertTrue(all(25 <= 27.7374-point[0] <= 28 and 2 <= 6.4192-point[1] <= 7
                            for _, vertices, _ in clipped for point in vertices))
        self.assertEqual(selected, before)

    def test_explicit_portal_layers_restore_base_floor_blocks_and_reference_ceiling(self):
        base = {'material': 'test', 'positions_m': [[26, 4, 0], [27, 4, 0], [26, 5, 0]],
                'faces': [[0, 1, 2]], 'room_number': 7}
        parts = [{**base, 'name': 'BASE_FLOOR', 'category': 'podlogi', 'superseded_by_finish': True},
                 {**base, 'name': 'BLOCK', 'category': 'wnetrze_bloki', 'interior_layer': 'blocks'},
                 {**base, 'name': 'CEILING', 'category': 'sufity'}]
        scene = {**self.scene, 'parts': self.parts + parts}
        selected = select_parts(scene, self.config, 'house', [p['name'] for p in parts])
        self.assertEqual([p['name'] for p, _, _ in selected], ['BASE_FLOOR', 'BLOCK', 'CEILING'])
        for actual, _, faces in selected:
            self.assertEqual(faces, actual['faces'])


if __name__ == '__main__':
    unittest.main()
