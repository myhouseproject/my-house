"""The photo-based bedroom must fit the unchanged room and retain all accesses."""
import unittest
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import MultiPoint, Polygon, box

from bedroom_geometry import build_bedroom, sample_textile_grid, textile_grid
from project_config import load_house_2d_model

ROOT = Path(__file__).resolve().parents[1]


class BedroomGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT/'modules/06_interior/extracts/bedroom.yaml').read_text())
        cls.parts = []
        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append(dict(name=name, category=category, material=material,
                                  mesh=mesh, assumed=assumed, **extras))
        build_bedroom(cls.cfg, collect)
        cls.by_name = {p['name']: p for p in cls.parts}
        frame = cls.cfg['frame']
        cls.origin = np.asarray(frame['origin_mm'])
        cls.basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])

    def local(self, mesh):
        return (mesh.vertices*1000-self.origin) @ self.basis

    def test_closed_finite_meshes_and_mobile_geometry_budget(self):
        self.assertGreater(len(self.parts), 25)
        self.assertEqual(len(self.by_name), len(self.parts))
        for part in self.parts:
            mesh = part['mesh']
            self.assertTrue(mesh.is_watertight, part['name'])
            self.assertTrue(mesh.is_winding_consistent, part['name'])
            self.assertGreater(mesh.volume, 0, part['name'])
            self.assertTrue(np.isfinite(mesh.vertices).all(), part['name'])
            self.assertIn(part['material'], self.cfg['render_materials'])
            self.assertIn(part['material'], self.cfg['material_properties'])
            self.assertEqual(part['room_number'], 8)
            self.assertEqual(part['interior_layer'], 'selected')
            self.assertTrue(part['bedroom_fixture'])
            self.assertTrue(part['assumed'])
            self.assertEqual(part['provenance']['type'], 'assumed')
        # Draped cloth is native geometry, while staying modest on mobile.
        self.assertLess(sum(len(p['mesh'].faces) for p in self.parts), 65000)

    def test_all_geometry_stays_inside_the_authoritative_bedroom(self):
        source = load_house_2d_model()['source_data']
        room = next(r for r in source['rooms'] if r['number'] == 8)
        allowed = Polygon(room['floor_reference_polygon_mm']).buffer(.01)
        for part in self.parts:
            footprint = MultiPoint(part['mesh'].vertices[:, :2]*1000).convex_hull
            self.assertTrue(allowed.covers(footprint), part['name'])
        floor = self.by_name['FIN_BEDROOM_FLOOR']['mesh']
        self.assertAlmostEqual(floor.bounds[1, 2], 0)
        ceiling = self.by_name['FIN_BEDROOM_CEILING']['mesh']
        self.assertAlmostEqual(ceiling.bounds[0, 2]*1000, self.cfg['room_reference']['ceiling_underside_mm'])

    def test_access_to_all_three_doors_and_both_bed_sides_is_open(self):
        checks = self.cfg['layout_checks']
        for key, bounds in checks.items():
            if not key.endswith('_clear_bounds_mm'):
                continue
            (x0, y0), (x1, y1) = bounds
            clear = box(x0, y0, x1, y1)
            for part in self.parts:
                if part.get('interior_finish') or part['category'] == 'sufity':
                    continue
                for component in part['mesh'].split(only_watertight=False):
                    vertices = self.local(component)
                    if vertices[:, 2].min() >= 2100 or vertices[:, 2].max() <= 0:
                        continue
                    footprint = MultiPoint(vertices[:, :2]).convex_hull
                    self.assertLess(footprint.intersection(clear).area, .1, f'{key}: {part["name"]}')

    def test_wall_finishes_do_not_cover_architectural_openings(self):
        # Project each actual surface triangle into its own declared wall plane.
        # Openings must have zero triangle area even when the whole wall is one U-shaped solid.
        for spec in self.cfg['surfaces']:
            if not spec.get('openings_uv_mm'):
                continue
            mesh = self.by_name[spec['id']]['mesh']
            vertices = self.local(mesh)
            u, v = spec['uv_axes']
            for hole in spec['openings_uv_mm']:
                opening = box(*hole).buffer(-.01)
                for face in mesh.faces:
                    triangle = Polygon(vertices[face][:, [u, v]])
                    if triangle.area > .0001:
                        self.assertLess(triangle.intersection(opening).area, .1, spec['id'])

    def test_mattress_is_full_size_and_bedding_has_native_drape(self):
        mattress = self.local(self.by_name['SEL_BEDROOM_MATTRESS']['mesh'])
        np.testing.assert_allclose(np.ptp(mattress, axis=0)[:2],
                                   self.cfg['layout_checks']['bed_mattress_size_mm'], rtol=.003)
        duvet = self.local(self.by_name['SEL_BEDROOM_DUVET']['mesh'])
        self.assertLess(duvet[:, 2].min(), 140)
        self.assertGreater(duvet[:, 2].max(), 580)
        self.assertGreater(len(np.unique(np.round(duvet[:, 2], 1))), 100)
        self.assertGreater(np.ptp(duvet, axis=0)[0], np.ptp(mattress, axis=0)[0])
        self.assertIn('SEL_BEDROOM_PILLOWS_OLIVE', self.by_name)
        self.assertFalse(any('BENCH' in name for name in self.by_name))

    def test_mural_uv_is_complete_and_only_the_room_facing_side_is_textured(self):
        part = self.by_name['FIN_BEDROOM_MURAL']
        mesh = part['mesh']
        uv = np.asarray(part['texture_uv'])
        self.assertEqual(uv.shape, (len(mesh.vertices), 2))
        self.assertTrue(np.all((uv >= 0) & (uv <= 1)))
        np.testing.assert_allclose(uv.min(axis=0), [0, 0])
        np.testing.assert_allclose(uv.max(axis=0), [1, 1])
        self.assertTrue(part['texture_url'].endswith('bedroom-cranes.jpg'))
        self.assertEqual(len(part['texture_faces']), 2)
        local = self.local(mesh)
        faces = mesh.faces[part['texture_faces']]
        np.testing.assert_allclose(local[faces, 1], local[:, 1].min())
        self.assertTrue(np.all(mesh.face_normals[part['texture_faces'], 1] < -.99))

    def test_throw_follows_duvet_without_crossing_or_hovering(self):
        specs = {spec['id']: spec for spec in self.cfg['elements']}
        duvet = textile_grid(specs['SEL_BEDROOM_DUVET']['textiles'][0], self.cfg['render'])
        spec = specs['SEL_BEDROOM_OLIVE_THROW']['textiles'][0]
        throw = textile_grid(spec, self.cfg['render'], duvet)
        lo, hi = np.asarray(spec['bounds_xy_mm'])
        x, y = np.meshgrid(np.linspace(lo[0], hi[0], 100), np.linspace(lo[1], hi[1], 100))
        clearance = sample_textile_grid(throw, x, y)-spec['thickness_mm']-sample_textile_grid(duvet, x, y)
        self.assertGreater(clearance.min(), 2)
        self.assertLess(clearance.max(), 17)

    def test_cream_table_tops_are_above_bodies_with_no_coincident_visible_top(self):
        for body_id, top_id in [('SEL_BEDROOM_NIGHTSTANDS', 'SEL_BEDROOM_NIGHTSTAND_TOPS'),
                                ('SEL_BEDROOM_CONSOLE', 'SEL_BEDROOM_CONSOLE_TOP')]:
            body = self.local(self.by_name[body_id]['mesh'])
            top = self.local(self.by_name[top_id]['mesh'])
            self.assertAlmostEqual(body[:, 2].max(), top[:, 2].min())
            self.assertGreater(top[:, 2].max()-body[:, 2].max(), 4)
            self.assertEqual(self.by_name[top_id]['material'], 'bedroom_floor')


if __name__ == '__main__':
    unittest.main()
