"""Bathroom concept must remain recognizable, local, and clear of the existing shell."""
import unittest

import numpy as np
import trimesh
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

    def test_selected_meshes_are_valid_and_manufacturer_objs_remain_exact(self):
        selected = [p for p in self.parts if p['category'] == 'wnetrze_elementy']
        self.assertGreater(len(selected), 15)
        signatures = set()
        procedural_faces = 0
        exact = []
        for p in selected:
            mesh = p['mesh']
            self.assertGreater(len(mesh.vertices), 0, p['name'])
            self.assertGreater(len(mesh.faces), 0, p['name'])
            self.assertTrue(np.isfinite(mesh.vertices).all(), p['name'])
            self.assertTrue(np.isfinite(mesh.faces).all(), p['name'])
            signature = (mesh.vertices.tobytes(), mesh.faces.tobytes())
            self.assertNotIn(signature, signatures, p['name'])
            signatures.add(signature)
            self.assertTrue(p['assumed'])
            self.assertEqual(p['room_number'], 7)
            self.assertEqual(p['provenance']['source_id'], 'bathroom-multiview-01')
            if p.get('manufacturer_geometry'):
                exact.append(p)
                self.assertEqual(p['product_status'], 'selected_manufacturer_obj')
                self.assertTrue(p['manufacturer_model_path'].endswith('.obj'))
            else:
                procedural_faces += len(mesh.faces)
                self.assertTrue(mesh.is_watertight, p['name'])
                self.assertTrue(mesh.is_winding_consistent, p['name'])
                self.assertGreater(mesh.volume, 0, p['name'])
        self.assertLess(procedural_faces, 40000)
        self.assertEqual(
            {p['name'] for p in exact},
            {'SEL_BATH_TUB_shell', 'SEL_BATH_TUB_faucet',
             'SEL_BATH_BASIN_1_faucet', 'SEL_BATH_BASIN_2_faucet',
             'SEL_BATH_SHOWER_system', 'SEL_BATH_BIDET_SPRAY'}
        )

    def test_bathtub_and_basins_have_real_cavities(self):
        for key in ('bathtub', 'basins'):
            spec = self.cfg['fixtures'][key]
            mesh = vessel_mesh(spec['profile_mm'], self.cfg['render']['ring_segments'], spec['exponent'],
                               rim_lift_mm=spec.get('rim_lift_mm'),
                               rim_lift_exponent=spec.get('rim_lift_exponent', 1))
            # Intersect a vertical ray through the centre with every triangle.
            # The first hit must be the inside floor, not a cap across the rim.
            triangles = mesh.triangles
            origin = np.array([0., 0., mesh.bounds[1, 2] + 100])
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
            highest_rim = max(z+lift for z, lift in zip(
                heights, spec.get('rim_lift_mm', [0]*len(heights))))
            self.assertGreater(outlet[2], highest_rim, key)

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
            if part.get('manufacturer_geometry'):
                # Official concealed fittings may legitimately extend behind the
                # finished wall. They must still stay in the immediate room envelope.
                self.assertTrue(polygon.buffer(300).covers(footprint), part['name'])
            else:
                self.assertTrue(polygon.buffer(.01).covers(footprint), part['name'])
                self.assertLess(footprint.intersection(walls).area, .01, part['name'])
            self.assertLess(footprint.intersection(doorway).area, .01, part['name'])
        self.assertEqual(room['floor_reference_polygon_mm'], [[25110,2169.2],[27737.4,2169.2],[27737.4,6419.2],[25110,6419.2]])

    def local_vertices_mm(self, part):
        frame = self.cfg['frame']
        basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
        return (part['mesh'].vertices*1000-np.asarray(frame['origin_mm'])) @ basis

    def test_bathtub_is_symmetrical_inverto_180x80(self):
        tub = next(p for p in self.parts if p['name'] == 'SEL_BATH_TUB_shell')
        spec = self.cfg['fixtures']['bathtub']
        placed = self.local_vertices_mm(tub)
        clearance = float(spec['corner_clearance_mm'])

        # The real rotated manufacturer mesh is held 200 mm off both walls
        # meeting at the W05/W06 window corner.
        self.assertAlmostEqual(placed[:, 0].min(), clearance, delta=1.0)
        self.assertAlmostEqual(
            self.cfg['room_reference']['depth_mm'] - placed[:, 1].max(),
            clearance, delta=1.0)
        self.assertLess(abs(float(spec['rotation_z_deg'])), 10.0)

        # Undo the authored plan rotation before checking catalogue dimensions
        # and symmetry of the exact Cersanit mesh.
        vertices = placed - np.asarray(spec['center_mm'], dtype=float)
        angle = np.deg2rad(float(spec['rotation_z_deg']))
        c, s = np.cos(angle), np.sin(angle)
        vertices[:, :2] = vertices[:, :2] @ np.array([[c, -s], [s, c]])
        half_length = np.max(vertices[:, 0])

        # Cersanit Inverto 180x80 (art. S301-372) is a symmetrical double-ended freestanding tub.
        right_end = vertices[vertices[:, 0] > half_length*.8, 2]
        left_end = vertices[vertices[:, 0] < -half_length*.8, 2]
        self.assertAlmostEqual(right_end.max(), left_end.max(), delta=2.0)
        # The manufacturer's OBJ is not stretched to nominal catalogue dimensions:
        # its measured mesh envelope is about 1791 x 794 x 636 mm.
        self.assertAlmostEqual(np.ptp(vertices[:, 0]), 1800.0, delta=15.0)
        self.assertAlmostEqual(np.ptp(vertices[:, 1]), 800.0, delta=15.0)
        self.assertAlmostEqual(np.ptp(vertices[:, 2]), 640.0, delta=15.0)

        # The official OBJ uses +Y as its physical up direction. After fitting,
        # the wider rim must be above the narrower base; otherwise the bath is upside down.
        z_min, z_max = vertices[:, 2].min(), vertices[:, 2].max()
        z_span = z_max - z_min
        bottom = vertices[vertices[:, 2] <= z_min + 0.10 * z_span]
        top = vertices[vertices[:, 2] >= z_max - 0.10 * z_span]
        self.assertGreater(np.ptp(top[:, 0]), np.ptp(bottom[:, 0]) * 1.15)
        self.assertGreater(np.ptp(top[:, 1]), np.ptp(bottom[:, 1]) * 1.15)

        # The faucet base sits wholly in the wall-to-tub strip, while the spout
        # reaches across the 200 mm tub clearance toward the rim.
        faucet = spec['faucet']
        foot = np.asarray(faucet['path_mm'][0], dtype=float)
        outlet = np.asarray(faucet['path_mm'][-1], dtype=float)
        wall_face = float(self.cfg['room_reference']['wall_finish_reference_mm'])
        self.assertGreater(foot[0] - faucet['foot_radius_mm'], wall_face)
        self.assertLess(foot[0] + faucet['foot_radius_mm'], clearance)
        self.assertGreater(outlet[0], clearance)

        self.assertFalse(any(p['name'] == 'SEL_BATH_TOWEL_STAND' for p in self.parts))

        # Preserve the manufacturer's topology exactly. The official Cersanit OBJ
        # contains open surfaces, so watertightness is not a valid requirement here.
        self.assertTrue(np.isfinite(tub['mesh'].vertices).all())
        self.assertGreater(len(tub['mesh'].faces), 0)

    def test_screen_spans_the_room_when_closed_and_opens_in_the_middle(self):
        screen = self.cfg['fixtures']['shower_screen']
        fixed = [p for p in screen['panels'] if p['operation'] == 'fixed']
        sliding = [p for p in screen['panels'] if p['operation'] == 'sliding']
        self.assertEqual(len(fixed), 2)
        self.assertEqual(len(sliding), 2)
        rail_half = screen['frame_width_mm']/2
        room_width = self.cfg['room_reference']['width_mm']
        midpoint = room_width/2
        opened_left, opened_right = [], []
        for panel in screen['panels']:
            x0, x1 = panel['x_mm']
            travel = panel.get('travel_x_mm', 0)
            parked = [x0+travel-rail_half, x1+travel+rail_half]
            (opened_left if sum(parked)/2 < midpoint else opened_right).append(parked)
            self.assertGreaterEqual(parked[0], 0)
            self.assertLessEqual(parked[1], room_width)
        actual_clear = [max(p[1] for p in opened_left), min(p[0] for p in opened_right)]
        self.assertGreater(actual_clear[1]-actual_clear[0], 650)
        np.testing.assert_allclose(screen['clear_opening_x_mm'], actual_clear, atol=.01)
        self.assertAlmostEqual(sum(actual_clear)/2, midpoint, places=3)

        # Intersect the emitted solid geometry at chest height. The closed screen
        # must have no permanently open side gap, including the panel frames.
        intervals = []
        frame = self.cfg['frame']
        basis = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
        for part in self.parts:
            if part['category'] != 'wnetrze_elementy' or part['bathroom_fixture'] != screen['id']:
                continue
            lines = trimesh.intersections.mesh_plane(part['mesh'], [0, 0, 1], [0, 0, 1.1])
            if len(lines):
                local = (lines*1000-np.asarray(frame['origin_mm'])) @ basis
                intervals.extend((float(xs.min()), float(xs.max())) for xs in local[:, :, 0])
        intervals.sort()
        self.assertTrue(intervals)
        self.assertAlmostEqual(intervals[0][0], min(p['x_mm'][0] for p in screen['panels'])-rail_half)
        covered_to = intervals[0][1]
        for left, right in intervals[1:]:
            self.assertLessEqual(left-covered_to, .01, 'An unintended permanent gap remains in the screen')
            covered_to = max(covered_to, right)
        self.assertAlmostEqual(covered_to, max(p['x_mm'][1] for p in screen['panels'])+rail_half)

    def test_toilet_has_an_unobstructed_approach(self):
        wc = self.cfg['fixtures']['toilet']
        bowl_parts = [p for p in self.parts if p['name'] in ('SEL_BATH_WC_bowl', 'SEL_BATH_WC_seat')]
        front_x = min(self.local_vertices_mm(p)[:, 0].min() for p in bowl_parts)
        # Design clearance for this concept, not a claim of code compliance.
        approach = box(front_x-650, wc['center_mm'][1]-350,
                       front_x, wc['center_mm'][1]+350)
        for part in self.parts:
            if part['category'] != 'wnetrze_elementy' or part['bathroom_fixture'] == wc['id']:
                continue
            vertices = self.local_vertices_mm(part)
            if vertices[:, 2].min() >= 1100 or vertices[:, 2].max() <= 0:
                continue
            footprint = MultiPoint(vertices[:, :2]).convex_hull
            self.assertLess(footprint.intersection(approach).area, .01, part['name'])

    def test_shower_fittings_are_attached_to_the_existing_wall(self):
        wall_face = (self.cfg['room_reference']['width_mm']
                     - self.cfg['room_reference']['wall_finish_reference_mm'])
        shower = next(p for p in self.parts if p['name'] == 'SEL_BATH_SHOWER_system')
        self.assertTrue(shower.get('manufacturer_geometry'))
        self.assertLess(abs(self.local_vertices_mm(shower)[:, 0].max() - wall_face), 120)
        self.assertFalse(any(p['name'] in ('SEL_BATH_SHOWER_head', 'SEL_BATH_SHOWER_mixer',
                                           'SEL_BATH_SHOWER_HANDSET')
                             for p in self.parts))
        drain = next(p for p in self.parts if p['name'] == 'SEL_BATH_LINEAR_DRAIN')
        drain_vertices = self.local_vertices_mm(drain)
        self.assertGreater(wall_face-drain_vertices[:, 0].max(), 0)
        self.assertLess(wall_face-drain_vertices[:, 0].max(), 20)
        self.assertFalse(any(p.get('bathroom_fixture') == 'BATH_SHOWER_LINING' for p in self.parts))
        # Removing the false wall must not remove the glass partition, bathtub,
        # or the independent WC furniture on the dry side of the room.
        fixtures = {p.get('bathroom_fixture') for p in self.parts if p['category'] == 'wnetrze_elementy'}
        self.assertTrue({'BATH_SCREEN', 'BATH_TUB', 'BATH_WC', 'BATH_WC_STORAGE'} <= fixtures)

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
