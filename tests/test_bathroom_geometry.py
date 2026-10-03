"""Bathroom concept must remain recognizable, local, and clear of the existing shell."""
import unittest

import numpy as np
from shapely.geometry import Polygon, MultiPoint, box
from shapely.ops import unary_union

from bathroom_geometry import build_bathroom, vessel_mesh
from export_scene_downloads import includes_part
from project_config import load_house_2d_model, load_house_3d_params, load_interior_model


class BathroomGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_interior_model()['bathroom']
        cls.parts = []
        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append({'name': name, 'category': category, 'material': material,
                              'mesh': mesh, 'assumed': assumed, **extras})
        build_bathroom(cls.cfg, collect)
        cls.house = load_house_2d_model()

    def test_all_selected_meshes_are_closed_and_well_oriented(self):
        selected = [p for p in self.parts if p['category'] == 'wnetrze_elementy']
        self.assertGreater(len(selected), 20)
        signatures = set()
        for p in selected:
            mesh = p['mesh']
            self.assertTrue(mesh.is_watertight, p['name'])
            self.assertTrue(mesh.is_winding_consistent, p['name'])
            self.assertGreater(mesh.volume, 0, p['name'])
            self.assertTrue(np.isfinite(mesh.vertices).all(), p['name'])
            signature = (mesh.vertices.tobytes(), mesh.faces.tobytes())
            self.assertNotIn(signature, signatures, p['name'])
            signatures.add(signature)
            self.assertTrue(p['assumed'])
            self.assertEqual(p['room_number'], 7)
            self.assertEqual(p['provenance']['source_id'], 'bathroom-reference')
        self.assertLess(sum(len(p['mesh'].faces) for p in selected), 40000)

    def test_bathtub_and_basins_have_real_cavities(self):
        for key in ('bathtub', 'basins'):
            spec = self.cfg['fixtures'][key]
            mesh = vessel_mesh(spec['profile_mm'], self.cfg['render']['ring_segments'], spec['exponent'])
            # Intersect a vertical ray through the centre with every triangle.
            # The first hit must be the inside floor, not a cap across the rim.
            triangles = mesh.triangles
            origin = np.array([0., 0., max(v[2] for v in spec['profile_mm']) + 100])
            direction = np.array([0., 0., -1.])
            edge1, edge2 = triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0]
            h = np.cross(direction, edge2)
            determinant = np.einsum('ij,ij->i', edge1, h)
            mask = np.abs(determinant) > 1e-8
            inverse = np.zeros_like(determinant); inverse[mask] = 1/determinant[mask]
            s = origin-triangles[:, 0]
            u = inverse*np.einsum('ij,ij->i', s, h)
            q = np.cross(s, edge1)
            v = inverse*(q @ direction)
            t = inverse*np.einsum('ij,ij->i', edge2, q)
            hits = mask & (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8) & (t >= 0)
            first_z = origin[2]-np.min(t[hits])
            self.assertAlmostEqual(first_z, spec['profile_mm'][-1][2], places=6)
            self.assertTrue(mesh.is_watertight)

    def test_faucet_outlets_are_over_the_inside_of_each_bowl(self):
        for key in ('bathtub', 'basins'):
            spec = self.cfg['fixtures'][key]
            heights = [row[2] for row in spec['profile_mm']]
            rim_z = max(heights)
            inner_rim = [row for row in spec['profile_mm'] if row[2] == rim_z][-1]
            if key == 'bathtub':
                outlet = np.asarray(spec['faucet']['path_mm'][-1])-spec['center_mm']
            else:
                outlet = np.asarray(spec['faucet']['path_relative_mm'][-1])
            distance = abs(outlet[0]/(inner_rim[0]/2))**spec['exponent'] + abs(outlet[1]/(inner_rim[1]/2))**spec['exponent']
            self.assertLess(distance, 1, key)
            self.assertGreater(outlet[2], rim_z)

    def test_existing_room_shell_openings_and_door_remain_clear(self):
        room = next(r for r in self.house['source_data']['rooms'] if r['number'] == 7)
        polygon = Polygon(room['floor_reference_polygon_mm'])
        walls = unary_union([Polygon(p['polygon_mm']) for p in self.house['source_data']['wall_cut_profiles']])
        door = next(d for d in self.house['source_data']['doors'] if d['id'] == self.cfg['room_reference']['entrance_id'])
        doorway = box(*door['core_opening_bbox_mm'])
        for part in self.parts:
            if part['category'] != 'wnetrze_elementy':
                continue
            xy = part['mesh'].vertices[:, :2]*1000
            footprint = MultiPoint(xy).convex_hull
            self.assertTrue(polygon.buffer(.01).covers(footprint), part['name'])
            self.assertLess(footprint.intersection(walls).area, .01, part['name'])
            self.assertLess(footprint.intersection(doorway).area, .01, part['name'])
        self.assertEqual(room['floor_reference_polygon_mm'], [[25110,2169.2],[27737.4,2169.2],[27737.4,6419.2],[25110,6419.2]])

    def test_export_variants_keep_blocks_separate_from_equipment(self):
        visual = [p for p in self.parts if includes_part(p, exterior=False, variant='visual')]
        blocks = [p for p in self.parts if includes_part(p, exterior=False, variant='blocks')]
        self.assertTrue(visual)
        self.assertEqual(len(blocks), len(self.cfg['blocks']))
        self.assertTrue(all(p['category'] == 'wnetrze_elementy' for p in visual))
        self.assertTrue(all(p['category'] == 'wnetrze_bloki' for p in blocks))
        self.assertFalse(any(includes_part(p, exterior=False, variant='shell') for p in self.parts))

    def test_ceiling_fittings_reach_current_ceiling_and_glass_is_transparent(self):
        ceiling = load_house_3d_params()['ceiling_level_mm']
        pendants, shower = self.cfg['fixtures']['pendants'], self.cfg['fixtures']['shower']
        self.assertEqual(pendants['canopy_z_mm']+pendants['canopy_height_mm'], ceiling)
        self.assertEqual(shower['stem_top_z_mm'], ceiling)
        materials = load_interior_model()['render_materials']
        self.assertLess(materials[self.cfg['fixtures']['shower_screen']['glazing_material']][3], .4)


if __name__ == '__main__':
    unittest.main()
