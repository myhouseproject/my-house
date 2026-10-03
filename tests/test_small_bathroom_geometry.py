"""Reference-based equipment must fit the unchanged bathroom/laundry shell."""
import unittest
from pathlib import Path

import numpy as np
import yaml
from shapely.geometry import MultiPoint, Polygon, box
from shapely.ops import unary_union

from bathroom_geometry import vessel_mesh
from small_bathroom_geometry import build_small_bathroom
from project_config import load_house_2d_model

ROOT = Path(__file__).resolve().parents[1]


class SmallBathroomGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = yaml.safe_load((ROOT/'modules/06_interior/extracts/small-bathroom.yaml').read_text())
        cls.parts = []
        def collect(name, category, material, mesh, source, assumed, note, source_id, extras):
            cls.parts.append(dict(name=name, category=category, material=material,
                                  mesh=mesh, assumed=assumed, **extras))
        build_small_bathroom(cls.cfg, collect)
        cls.parts_by_name = {p['name']: p for p in cls.parts}
        frame = cls.cfg['frame']
        cls.basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
        cls.origin = np.asarray(frame['origin_mm'])

    def local(self, mesh):
        return (mesh.vertices*1000-self.origin) @ self.basis

    def test_closed_finite_positive_meshes_and_declared_materials(self):
        self.assertGreater(len(self.parts), 40)
        self.assertEqual(len(self.parts_by_name), len(self.parts))
        fingerprints = set()
        for part in self.parts:
            mesh = part['mesh']
            self.assertTrue(mesh.is_watertight, part['name'])
            self.assertTrue(mesh.is_winding_consistent, part['name'])
            self.assertGreater(mesh.volume, 0, part['name'])
            self.assertTrue(np.isfinite(mesh.vertices).all(), part['name'])
            self.assertIn(part['material'], self.cfg['render_materials'])
            self.assertIn(part['room_number'], [2, 3])
            self.assertTrue(part['assumed'])
            self.assertIn(part['provenance']['source_id'], self.cfg['provenance']['source_ids'])
            fingerprint = (mesh.vertices.tobytes(), mesh.faces.tobytes())
            self.assertNotIn(fingerprint, fingerprints, part['name'])
            fingerprints.add(fingerprint)
        self.assertLess(sum(len(p['mesh'].faces) for p in self.parts), 45000)

    def test_room_shell_and_entry_passage_are_preserved(self):
        house = load_house_2d_model()['source_data']
        rooms = {r['number']: Polygon(r['floor_reference_polygon_mm'])
                 for r in house['rooms'] if r['number'] in (2, 3)}
        # The 150 mm open passage is not included in either room's reference polygon.
        passage = box(16610, 4620, 16760, 5620)
        walls = unary_union([Polygon(p['polygon_mm']) for p in house['wall_cut_profiles']])
        doorway = box(*next(d['core_opening_bbox_mm'] for d in house['doors'] if d['id'] == 'DR08'))
        for part in self.parts:
            allowed = unary_union([rooms[part['room_number']], passage]).buffer(.01)
            for component in part['mesh'].split(only_watertight=False):
                footprint = MultiPoint(component.vertices[:, :2]*1000).convex_hull
                self.assertTrue(allowed.covers(footprint), part['name'])
                self.assertLess(footprint.intersection(walls).area, .1, part['name'])
                self.assertLess(footprint.intersection(doorway).area, .1, part['name'])

    def test_declared_approaches_are_not_blocked_by_furniture(self):
        checks = self.cfg['layout_checks']
        for check in ('wc_approach_bounds_mm', 'passage_clear_bounds_mm', 'door_clear_bounds_mm', 'shower_entry_bounds_mm'):
            (x0, y0), (x1, y1) = checks[check]
            area = box(x0, y0, x1, y1)
            for part in self.parts:
                if part.get('bathroom_finish') or part['category'] == 'sufity':
                    continue
                local = self.local(part['mesh'])
                if local[:, 2].max() <= 5 or local[:, 2].min() >= 2050:
                    continue
                for component in part['mesh'].split(only_watertight=False):
                    vertices = self.local(component)
                    if vertices[:, 2].min() >= 2050:
                        continue
                    footprint = MultiPoint(vertices[:, :2]).convex_hull
                    self.assertLess(footprint.intersection(area).area, .1, f'{check}: {part["name"]}')

    def test_open_basin_has_a_low_inside_floor_and_outlet_over_bowl(self):
        spec = next(e for e in self.cfg['elements'] if e['id'] == 'SEL_SMALL_BATH_BASIN_BOWL')['vessels'][0]
        mesh = vessel_mesh(spec['profile_mm'], self.cfg['render']['ring_segments'], spec['exponent'])
        # A vertical ray through the centre must hit the bowl floor, not a sealed rim.
        origin = np.array([0., 0., 400.]); direction = np.array([0., 0., -1.])
        triangles = mesh.triangles
        e1, e2 = triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0]
        cross = np.cross(direction, e2); determinant = np.einsum('ij,ij->i', e1, cross)
        mask = np.abs(determinant) > 1e-8
        inv = np.zeros_like(determinant); inv[mask] = 1/determinant[mask]
        s = origin-triangles[:, 0]; u = inv*np.einsum('ij,ij->i', s, cross)
        q = np.cross(s, e1); v = inv*(q@direction); t = inv*np.einsum('ij,ij->i', e2, q)
        hits = mask & (u >= -1e-8) & (v >= -1e-8) & (u+v <= 1+1e-8) & (t >= 0)
        self.assertAlmostEqual(origin[2]-min(t[hits]), 30)
        outlet = np.asarray(self.cfg['layout_checks']['basin_outlet_mm'])-spec['center_mm']
        inside_rim = [r for r in spec['profile_mm'] if r[2] == 140][-1]
        normalized = abs(outlet[0]/(inside_rim[0]/2))**spec['exponent'] + abs(outlet[1]/(inside_rim[1]/2))**spec['exponent']
        self.assertLess(normalized, 1)
        self.assertGreater(outlet[2], 140)

    def test_floor_tile_and_grout_faces_are_separate_and_bridge_passage(self):
        for room in ('R02', 'R03', 'PASSAGE'):
            tiles = self.parts_by_name[f'FIN_SMALL_BATH_{room}_FLOOR']['mesh']
            grout = self.parts_by_name[f'FIN_SMALL_BATH_{room}_FLOOR_GROUT']['mesh']
            self.assertAlmostEqual(tiles.bounds[1, 2], 0)
            self.assertAlmostEqual(tiles.bounds[0, 2], -.012)
            self.assertAlmostEqual(grout.bounds[1, 2], -.012)
            self.assertAlmostEqual(grout.bounds[0, 2], -.014)
        passage = self.parts_by_name['FIN_SMALL_BATH_PASSAGE_FLOOR_GROUT']['mesh']
        np.testing.assert_allclose(passage.bounds[:, :2]*1000, [[16610, 4620], [16760, 5620]])
        for part in self.parts:
            if part['category'] == 'sufity':
                self.assertAlmostEqual(part['mesh'].bounds[0, 2], 2.6)
                self.assertAlmostEqual(part['mesh'].bounds[1, 2], 2.62)

    def test_mirror_is_round_and_laundry_contains_no_invented_appliances(self):
        mirror = self.local(self.parts_by_name['SEL_SMALL_BATH_MIRROR']['mesh'])
        size = np.ptp(mirror, axis=0)
        self.assertAlmostEqual(size[1], size[2])
        self.assertAlmostEqual(size[0], 8)
        ids = set(self.parts_by_name)
        self.assertIn('SEL_LAUNDRY_DRYING_RACK', ids)
        self.assertIn('SEL_LAUNDRY_LOUVRED_FRONT', ids)
        self.assertIn('SEL_LAUNDRY_RADIATOR', ids)
        self.assertFalse(any('WASHER' in id or 'DRYER' in id for id in ids))
        self.assertIn('SEL_SMALL_BATH_WC_SERVICE_NICHE', ids)
        self.assertIn('FIN_SMALL_BATH_SHOWER_NICHE_LINING', ids)


if __name__ == '__main__':
    unittest.main()
