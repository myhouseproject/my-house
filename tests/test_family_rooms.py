"""Spatial and render checks for the proposed rooms, against the existing shell."""
from pathlib import Path
import unittest

import numpy as np
from shapely.geometry import MultiPoint, Polygon, box

from bedroom_geometry import build_furnished_room
from project_config import load_house_2d_model, load_interior_model
from scripts.render_bathroom import load_configuration, select_parts, to_canonical_m

ROOT = Path(__file__).resolve().parents[1]
ROOMS = {'kids_room_1': ('kids-room-1', 4), 'kids_room_2': ('kids-room-2', 5),
         'wardrobe': ('wardrobe', 9), 'office': ('office', 15)}
# Existing door swings / entry landing zones in local coordinates, not new openings.
ENTRANCES = {4: [1125, 2750, 2125, 3740], 5: [750, 2750, 1750, 3740],
             9: [2550, 1740.8, 3580, 2940.8], 15: [1900, 2450, 2980, 3450]}


class FamilyRoomsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_interior_model()
        cls.rooms = {r['number']: r for r in load_house_2d_model()['source_data']['rooms']}
        cls.built = {}
        for key, (slug, number) in ROOMS.items():
            parts = []
            def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
                parts.append(dict(name=name, category=category, material=material, mesh=mesh,
                                  source=source, assumed=assumed, **extras))
            build_furnished_room(cls.model[key], collect)
            cls.built[key] = parts

    def test_room_containment_and_valid_mobile_meshes(self):
        all_names = []
        total_faces = 0
        for key, (_, number) in ROOMS.items():
            cfg = self.model[key]
            allowed = Polygon(self.rooms[number]['floor_reference_polygon_mm']).buffer(.02)
            parts = self.built[key]
            self.assertGreater(len(parts), 15, key)
            for part in parts:
                with self.subTest(room=key, part=part['name']):
                    mesh = part['mesh']
                    self.assertTrue(np.isfinite(mesh.vertices).all())
                    self.assertTrue(mesh.is_watertight)
                    self.assertTrue(mesh.is_winding_consistent)
                    self.assertGreater(mesh.volume, 0)
                    footprint = MultiPoint(mesh.vertices[:, :2]*1000).convex_hull
                    self.assertTrue(allowed.covers(footprint))
                    self.assertEqual(part['room_number'], number)
                    self.assertEqual(part['fixture_group'], key)
                    self.assertNotIn('bedroom_fixture', part)
                    self.assertTrue(part['assumed'])
                    self.assertEqual(part['provenance']['type'], 'assumed')
                    self.assertIn(part['material'], cfg['render_materials'])
                    self.assertIn(part['material'], cfg['material_properties'])
                    total_faces += len(mesh.faces)
                    all_names.append(part['name'])
        self.assertEqual(len(set(all_names)), len(all_names))
        self.assertLess(total_faces, 220000)

    def test_doors_and_entrance_landings_are_not_blocked_by_furniture(self):
        for key, (_, number) in ROOMS.items():
            origin = np.array(self.model[key]['frame']['origin_mm'])
            landing = box(*ENTRANCES[number]).buffer(-.1)
            for part in self.built[key]:
                if part.get('interior_finish') or part['category'] == 'sufity':
                    continue
                for component in part['mesh'].split(only_watertight=False):
                    vertices = component.vertices*1000-origin
                    if vertices[:, 2].max() <= 30 or vertices[:, 2].min() >= 2100:
                        continue
                    footprint = MultiPoint(vertices[:, :2]).convex_hull
                    self.assertLess(footprint.intersection(landing).area, .1,
                                    f'{key}: {part["name"]}')

    def test_wall_cladding_retains_window_and_door_openings(self):
        for key in ROOMS:
            cfg = self.model[key]
            origin = np.array(cfg['frame']['origin_mm'])
            by_name = {p['name']: p for p in self.built[key]}
            for spec in cfg['surfaces']:
                if not spec.get('openings_uv_mm'):
                    continue
                mesh = by_name[spec['id']]['mesh']
                vertices = mesh.vertices*1000-origin
                u, v = spec['uv_axes']
                for bounds in spec['openings_uv_mm']:
                    hole = box(*bounds).buffer(-.01)
                    for face in mesh.faces:
                        triangle = Polygon(vertices[face][:, [u, v]])
                        if triangle.area > .0001:
                            self.assertLess(triangle.intersection(hole).area, .1, spec['id'])

    def test_each_offline_profile_keeps_its_actual_room_and_materials(self):
        for key, (slug, number) in ROOMS.items():
            config = load_configuration(ROOT/f'modules/06_interior/extracts/{slug}-render.yaml')
            parts = [{**{k: v for k, v in p.items() if k != 'mesh'},
                      'positions_m': p['mesh'].vertices.tolist(), 'faces': p['mesh'].faces.tolist()}
                     for room_parts in self.built.values() for p in room_parts]
            scene = dict(units='m', up_axis='Z', coordinate_frame='building_local', parts=parts)
            selected = select_parts(scene, config, scope='room')
            self.assertEqual({p['name'] for p, _, _ in selected},
                             {p['name'] for p in self.built[key]})
            for part, vertices, _ in selected:
                self.assertIn(part['material'], config['materials'])
                np.testing.assert_allclose([to_canonical_m(v, config['frame']) for v in vertices],
                                           part['positions_m'], atol=1e-12)


if __name__ == '__main__':
    unittest.main()
