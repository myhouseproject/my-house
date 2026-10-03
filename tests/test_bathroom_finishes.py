"""Finish panels preserve the real shell, openings and finished floor datum."""
import unittest

import numpy as np
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from bathroom_geometry import build_bathroom
from project_config import load_house_2d_model, load_house_3d_params, load_interior_model


class BathroomFinishesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        interior = load_interior_model()
        cls.room = interior['bathroom']
        cls.cfg = interior['bathroom_finishes']
        cls.materials = interior['render_materials']
        cls.parts = []
        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append({'name': name, 'category': category, 'material': material,
                              'mesh': mesh, 'assumed': assumed, **extras})
        build_bathroom(cls.room, collect, finishes=cls.cfg)
        cls.finishes = [p for p in cls.parts if p.get('bathroom_finish')]
        frame = cls.room['frame']
        cls.origin = np.asarray(frame['origin_mm'])
        cls.basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])

    def local_vertices(self, part):
        return (part['mesh'].vertices*1000-self.origin) @ self.basis

    def planar_coverage(self, parts, axes, top_z=None):
        faces = []
        for part in parts:
            vertices = self.local_vertices(part)
            for triangle in vertices[part['mesh'].faces]:
                if top_z is not None and not np.allclose(triangle[:, 2], top_z):
                    continue
                polygon = Polygon(triangle[:, axes])
                if polygon.area > 1e-8:
                    faces.append(polygon)
        return unary_union(faces)

    def test_all_finish_geometry_is_closed_local_and_has_explicit_materials(self):
        self.assertGreater(len(self.finishes), 20)
        for part in self.finishes:
            mesh = part['mesh']
            self.assertTrue(mesh.is_watertight, part['name'])
            self.assertTrue(mesh.is_winding_consistent, part['name'])
            self.assertGreater(mesh.volume, 0, part['name'])
            self.assertTrue(np.isfinite(mesh.vertices).all(), part['name'])
            vertices = self.local_vertices(part)
            self.assertGreaterEqual(vertices[:, 0].min(), -.001, part['name'])
            self.assertLessEqual(vertices[:, 0].max(), 2627.401, part['name'])
            self.assertGreaterEqual(vertices[:, 1].min(), -.001, part['name'])
            self.assertLessEqual(vertices[:, 1].max(), 4250.001, part['name'])
            self.assertGreaterEqual(vertices[:, 2].min(), -10.001, part['name'])
            self.assertLessEqual(vertices[:, 2].max(), 2865.001, part['name'])
            self.assertIn(part['material'], self.materials)
            self.assertEqual(part['room_number'], 7)
            self.assertEqual(part['material_status'], 'concept_palette_not_selected_product')
            self.assertEqual(part['provenance']['type'], 'assumed')
        self.assertLess(sum(len(p['mesh'].faces) for p in self.finishes), 10000)

    def test_window_and_door_openings_are_not_covered_by_finish_panels(self):
        source = load_house_2d_model()['source_data']
        params = load_house_3d_params()
        for opening_id, surface_id, uv_axes, height in (
                ('W05', 'SOUTH_WET_WALL', [0, 2], params['window_top_level_mm']),
                ('W06', 'EAST_WET_WALL', [1, 2], params['window_top_level_mm']),
                ('DR12', 'NORTH_ENTRY_WALL', [0, 2], params['door_opening_height_mm'])):
            records = source['windows'] if opening_id.startswith('W') else source['doors']
            opening = next(o for o in records if o['id'] == opening_id)
            x0, y0, x1, y1 = opening['core_opening_bbox_mm']
            local = (np.array([[x0, y0, 0], [x1, y1, 0]])-self.origin) @ self.basis
            axis = uv_axes[0]
            aperture = box(local[:, axis].min(), 0, local[:, axis].max(), height)
            parts = [p for p in self.finishes if p['finish_surface'] == surface_id]
            self.assertTrue(parts)
            finish = self.planar_coverage(parts, uv_axes)
            self.assertLess(finish.intersection(aperture).area, .01, opening_id)
            self.assertGreater(finish.area, 0, opening_id)

    def test_shower_wall_is_tiled_without_a_false_wall_or_niche(self):
        parts = [p for p in self.finishes if p['finish_surface'] == 'WEST_WET_WALL']
        self.assertTrue(parts)
        coverage = self.planar_coverage(parts, [1, 2])
        # The old shelf aperture must now be covered; no empty recess or facing
        # remains suspended at the removed false wall's position.
        self.assertTrue(coverage.covers(box(2620, 1250, 3910, 1530)))
        self.assertTrue(coverage.covers(box(2340, 0, 4235, 2850)))
        wall_face = (self.room['room_reference']['width_mm']
                     - self.cfg['room_reference']['wall_finish_mm'])
        for part in parts:
            self.assertGreaterEqual(self.local_vertices(part)[:, 0].min(), wall_face-.001)
        self.assertFalse(any(p['name'] == 'SEL_BATH_SHOWER_niche_lining' for p in self.parts))
        self.assertFalse(any(p.get('finish_surface') == 'WEST_NICHE_FACE' for p in self.finishes))

    def test_tiles_and_grout_are_real_geometry_and_preserve_floor_zero(self):
        tile = next(p for p in self.finishes if p['name'] == 'FIN_BATH_FLOOR_tiles')
        grout = next(p for p in self.finishes if p['name'] == 'FIN_BATH_FLOOR_grout')
        self.assertAlmostEqual(self.local_vertices(tile)[:, 2].max(), 0)
        self.assertLess(self.local_vertices(grout)[:, 2].max(), 0)
        surface = next(s for s in self.cfg['surfaces'] if s['id'] == 'FLOOR')
        u, v = surface['grid_origin_uv_mm']
        top = self.planar_coverage([tile], [0, 1], top_z=0)
        gap = self.cfg['tile_layout']['grout_width_mm']
        self.assertFalse(top.covers(Point(u, v+100)))
        self.assertTrue(top.covers(Point(u+gap, v+100)))
        self.assertLess(top.area, 2627.4*4250)
        self.assertGreater(top.area, .99*2627.4*4250)

    def test_ceiling_uses_ceiling_visibility_category(self):
        ceiling = next(p for p in self.finishes if p['finish_role'] == 'ceiling')
        self.assertEqual(ceiling['category'], 'sufity')
        self.assertAlmostEqual(self.local_vertices(ceiling)[:, 2].min(), load_house_3d_params()['ceiling_level_mm'])
        lights = [p for p in self.finishes if p['finish_role'] == 'ceiling_light']
        self.assertTrue(lights)
        self.assertTrue(all(p['category'] == 'wnetrze_elementy' for p in lights))


if __name__ == '__main__':
    unittest.main()
