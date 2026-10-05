from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import project_config
from bedroom_geometry import build_furnished_room


class OfficeAIDesignerGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.office = project_config.load_interior_model()['office']
        cls.parts = []

        def collect(name, category, material, mesh, source, assumed=False, note='', source_id='', extras=None, **kwargs):
            metadata = dict(extras or {})
            metadata.update(kwargs)
            cls.parts.append({
                'name': name,
                'category': category,
                'material': material,
                'mesh': mesh,
                **metadata,
            })

        build_furnished_room(cls.office, collect, include_design_variants=True)

    def test_all_declared_variants_are_generated(self):
        expected = {v['key'] for v in self.office['design_variants']['variants']}
        actual = {p.get('ai_variant_key') for p in self.parts if p.get('ai_candidate')}
        self.assertEqual(actual, expected)

    def test_ai_variants_stay_inside_exact_r15_room(self):
        origin = self.office['frame']['origin_mm']
        width, depth = self.office['room_reference']['bounds_mm'][1]
        eps = 1e-6
        for part in self.parts:
            if not part.get('ai_candidate'):
                continue
            vertices = part['mesh'].vertices
            x0, x1 = vertices[:, 0].min() * 1000 - origin[0], vertices[:, 0].max() * 1000 - origin[0]
            y0, y1 = vertices[:, 1].min() * 1000 - origin[1], vertices[:, 1].max() * 1000 - origin[1]
            self.assertGreaterEqual(x0, -eps, part['name'])
            self.assertLessEqual(x1, width + eps, part['name'])
            self.assertGreaterEqual(y0, -eps, part['name'])
            self.assertLessEqual(y1, depth + eps, part['name'])

    def test_floor_furniture_does_not_block_declared_entrance_zone(self):
        origin = self.office['frame']['origin_mm']
        (ex0, ey0), (ex1, ey1) = self.office['circulation']['entrance_clear_bounds_mm']
        floor_groups = {'desk', 'chair', 'sofa', 'rug', 'storage'}
        for part in self.parts:
            if not part.get('ai_candidate') or part.get('ai_design_group') not in floor_groups:
                continue
            vertices = part['mesh'].vertices
            x0, x1 = vertices[:, 0].min() * 1000 - origin[0], vertices[:, 0].max() * 1000 - origin[0]
            y0, y1 = vertices[:, 1].min() * 1000 - origin[1], vertices[:, 1].max() * 1000 - origin[1]
            overlaps = x0 < ex1 and x1 > ex0 and y0 < ey1 and y1 > ey0
            self.assertFalse(overlaps, f"{part['name']} overlaps the office entrance clear zone")


if __name__ == '__main__':
    unittest.main()
