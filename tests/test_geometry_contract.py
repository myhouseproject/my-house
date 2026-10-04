"""Behavioral checks for the canonical local model and separated exports."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import trimesh
from shapely.geometry import box
from shapely.ops import unary_union

import generuj_geometrie as generator
from export_scene_downloads import build_download_scene


class CanonicalGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        # A real local build must not even load the environment configuration.
        with patch.object(generator, 'load_terrain_model', side_effect=AssertionError('terrain dependency')):
            with patch.object(generator, 'load_garden_model', side_effect=AssertionError('garden dependency')):
                with contextlib.redirect_stdout(io.StringIO()):
                    cls.source = generator.main(scope='interior', output_dir=cls.temp.name, preview=False)
        cls.parts = {p['name']: p for p in cls.source['parts']}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_local_build_preserves_source_dimensions_without_map_scale(self):
        self.assertEqual(self.source['coordinate_frame'], 'building_local')
        self.assertFalse(self.source['map_transform_applied'])
        room = next(r for r in generator.DATA['rooms'] if r['id'] == 'R11')
        floor = next(p for p in self.source['parts'] if p['source_id'] == 'R11' and p['category'] == 'podlogi')
        expected = np.asarray(room['floor_reference_polygon_mm'], dtype=float) / 1000
        actual = np.asarray(floor['positions_m'], dtype=float)[:, :2]
        # Check source points and pairwise distances, not a rotated bounding box.
        for point in expected:
            self.assertLess(float(np.min(np.linalg.norm(actual-point, axis=1))), 1e-6)
        self.assertAlmostEqual(float(np.linalg.norm(expected[1]-expected[0])), 5.95, places=6)
        self.assertFalse((Path(self.temp.name) / 'scena_modelu.json').exists())

    def test_local_glb_variants_never_mix_furniture_layers(self):
        for variant, expected, forbidden in (
            ('visual', 'wnetrze_elementy', 'wnetrze_bloki'),
            ('blocks', 'wnetrze_bloki', 'wnetrze_elementy'),
            ('shell', 'sciany', 'wnetrze_elementy'),
        ):
            scene = build_download_scene(self.source, exterior=False, variant=variant)
            categories = {self.parts[mesh.metadata.get('source_part', name)]['category']
                          for name, mesh in scene.geometry.items()}
            self.assertIn(expected, categories)
            self.assertNotIn(forbidden, categories)
            if variant == 'shell':
                self.assertNotIn('wnetrze_bloki', categories)
            self.assertNotIn('lica_wykonczenia', categories)
        mapped = {**self.source, 'coordinate_frame': 'georeferenced'}
        with self.assertRaisesRegex(ValueError, 'scena_lokalna'):
            build_download_scene(mapped, exterior=False)

    def test_current_meshes_have_truthful_validation_and_no_duplicate_furniture(self):
        seen = {}
        for part in self.source['parts']:
            self.assertIsNone(part['valid_brep'])
            self.assertEqual(part['geometry_representation'], 'triangle_mesh')
            if part['geometry'] == 'solid':
                self.assertTrue(part['watertight_mesh'], part['name'])
            if part['category'] != 'wnetrze_elementy':
                continue
            signature = json.dumps([part['positions_m'], part['faces']], sort_keys=True)
            self.assertNotIn(signature, seen, f"Duplicated {part['name']} and {seen.get(signature)}")
            seen[signature] = part['name']

    def test_product_dimensions_are_not_certified_installed_openings(self):
        window = next(p for p in self.source['parts'] if p['source_id'] == 'W01')
        self.assertFalse(window['installation_verified'])
        self.assertIsNone(window['installation_clearance_mm'])
        self.assertEqual(window['product_dimensions_mm']['width'], 1770)
        self.assertIn('opening_model_dimensions_mm', window)
        self.assertTrue(window['assumed'])

    def test_bedroom_entrance_view_cuts_in_front_of_console_wall_panel(self):
        bedroom = generator.INTERIOR_MODEL['bedroom']
        inset = generator.INTERIOR_MODEL['viewer_presets']['bedroom']['entrance_cut_inset_mm']
        clip_y = (bedroom['frame']['origin_mm'][1] + inset) / 1000
        panel = self.parts['FIN_BEDROOM_SOUTH_PANEL']
        self.assertLess(max(vertex[1] for vertex in panel['positions_m']), clip_y)

    def test_finish_reference_preserves_open_plan_edge(self):
        room = box(0, 0, 5950, 3440)
        walls = unary_union([box(-300, -300, 0, 3740), box(0, -300, 5950, 0), box(0, 3440, 5950, 3740)])
        finished = generator.finished_room_reference(room, walls, 15)
        self.assertEqual(finished.bounds, (15, 15, 5950, 3425))
        self.assertEqual(room.bounds, (0, 0, 5950, 3440))
        self.assertAlmostEqual(finished.area, 5935*3410)

    def test_finish_edge_overrides_only_change_physical_faces(self):
        room = box(0, 0, 5950, 3440)
        walls = unary_union([box(-300, -300, 0, 3740), box(0, -300, 5950, 0), box(0, 3440, 5950, 3740)])
        coordinates = list(room.exterior.coords)
        left = next(i for i, (a, b) in enumerate(zip(coordinates, coordinates[1:])) if a[0] == b[0] == 0)
        open_edge = next(i for i, (a, b) in enumerate(zip(coordinates, coordinates[1:])) if a[0] == b[0] == 5950)
        same = generator.finished_room_reference(room, walls, 15, [{'edge_index': left, 'thickness_mm': 15}])
        self.assertLess(same.symmetric_difference(generator.finished_room_reference(room, walls, 15)).area, 1e-5)
        finished = generator.finished_room_reference(room, walls, 15, [
            {'edge_index': left, 'thickness_mm': 25}, {'edge_index': open_edge, 'thickness_mm': 100}])
        self.assertEqual(finished.bounds, (25, 15, 5950, 3425))

    def test_art_wall_finish_does_not_cover_door_opening(self):
        pieces = [p for p in self.source['parts'] if p['source_id'] == 'SEL_ART_concrete']
        self.assertEqual(len(pieces), 2)
        below_lintel = next(p for p in pieces if p['z_bottom_mm'] == 0)
        self.assertEqual(below_lintel['clipped_to_openings'], ['DR11'])
        self.assertAlmostEqual(max(p[0] for p in below_lintel['positions_m']), 19.06)
        above_lintel = next(p for p in pieces if p['z_bottom_mm'] != 0)
        self.assertAlmostEqual(max(p[0] for p in above_lintel['positions_m']), 20.06)

    def test_map_affine_is_explicit_and_does_not_modify_local_source(self):
        record = copy.deepcopy(next(p for p in self.source['parts'] if p['category'] == 'sciany'))
        original = np.asarray(record['positions_m'], dtype=float)
        mesh = trimesh.Trimesh(vertices=original.copy(), faces=record['faces'], process=False)
        affine = np.array([[0, -.9993, 12000], [.9993, 0, -5000], [0, 0, 1]])
        geo = {'status': 'fetched', 'alignment': {'house_calibration': {
            'model_to_geo_local_affine_mm': affine.tolist()}}}
        with patch.object(generator, 'parts', [record]), patch.object(generator, 'meshes', {record['name']: mesh}):
            with patch.object(generator, 'GEO_REAL', geo), contextlib.redirect_stdout(io.StringIO()):
                generator.apply_georeference_to_all_project_layers()
        expected_xy = np.column_stack([original[:, :2]*1000, np.ones(len(original))]) @ affine.T
        np.testing.assert_allclose(mesh.vertices[:, :2], expected_xy[:, :2]/1000)
        np.testing.assert_allclose(mesh.vertices[:, 2], original[:, 2])
        np.testing.assert_array_equal(self.parts[record['name']]['positions_m'], original)

    def test_room_override_and_finished_reference_reach_generated_geometry(self):
        model = copy.deepcopy(generator.INTERIOR_MODEL)
        policy = model.setdefault('room_policies', {}).setdefault('R01', {})
        policy['ceiling'] = {'level_parameter': 'finished_ceiling_height_mm', 'override_level_mm': 2725,
                             'status': 'project'}
        policy['finished_faces'] = {'reference_wall_finish_thickness_mm': 15,
                                    'source_id': 'architecture-primary', 'decision_id': 'D-FINISHES'}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(generator, 'INTERIOR_MODEL', model), contextlib.redirect_stdout(io.StringIO()):
                source = generator.main(scope='house', output_dir=directory, preview=False)
        ceiling = next(p for p in source['parts'] if p['source_id'] == 'R01' and p['category'] == 'sufity')
        np.testing.assert_allclose(np.asarray(ceiling['positions_m'])[:, 2], 2.725)
        finish = next(p for p in source['parts'] if p['source_id'] == 'R01' and p['category'] == 'lica_wykonczenia')
        self.assertFalse(finish['default_visible'])
        reference = finish['finish_reference']
        self.assertEqual(reference['wall_finish_thickness_mm'], 15)
        self.assertLess(reference['finished_reference_area_m2'], reference['raw_area_m2'])


if __name__ == '__main__':
    unittest.main()
