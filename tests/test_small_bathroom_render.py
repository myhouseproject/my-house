"""A second authored room must survive local selection and portal house rendering."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np
import yaml

from scripts.render_bathroom import (
    DEFAULT_CONFIG, load_configuration, material_spec, select_parts,
    shader_coordinate_transform, to_canonical_m, to_local_m,
)

SMALL_CONFIG = DEFAULT_CONFIG.with_name('small-bathroom-render.yaml')


class SmallBathroomRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.small = load_configuration(SMALL_CONFIG)
        cls.main = load_configuration(DEFAULT_CONFIG)

    @staticmethod
    def fixture(name, room, vertices, **extras):
        return {'name': name, 'room_number': room, 'category': 'wnetrze_wybrane',
                'interior_layer': 'selected', 'bathroom_fixture': True,
                'material': 'small_bathroom_ceramic', 'positions_m': vertices,
                'faces': [[0, 1, 2]], **extras}

    def test_two_room_scope_keeps_laundry_and_bathroom_in_exact_canonical_positions(self):
        parts = [
            self.fixture('SMALL_WC', 3, [[17.2, 4, 0], [17.8, 4, 0], [17.2, 4.5, 0]]),
            self.fixture('LAUNDRY_CABINET', 2, [[15.2, 4, 0], [15.8, 4, 0], [15.2, 4.5, 0]]),
            self.fixture('SMALL_FLOOR', 3, [[17, 4, 0], [18, 4, 0], [17, 5, 0]], bathroom_finish=True),
            self.fixture('OTHER_BATHROOM', 7, [[25, 4, 0], [26, 4, 0], [25, 5, 0]]),
        ]
        scene = {'units': 'm', 'up_axis': 'Z', 'coordinate_frame': 'building_local', 'parts': parts}
        before = copy.deepcopy(scene)
        selected = select_parts(scene, self.small)
        self.assertEqual({part['name'] for part, _, _ in selected},
                         {'SMALL_WC', 'LAUNDRY_CABINET', 'SMALL_FLOOR'})
        for part, vertices, faces in selected:
            restored = [to_canonical_m(point, self.small['frame']) for point in vertices]
            np.testing.assert_allclose(restored, part['positions_m'], atol=1e-12)
            self.assertEqual(faces, part['faces'])
        self.assertEqual(scene, before)

    def test_house_imports_both_room_optics_and_transforms_lights_once(self):
        house = load_configuration(DEFAULT_CONFIG, scope='house')
        self.assertEqual(house['materials']['bathroom_tile_marble'],
                         self.main['materials']['bathroom_tile_marble'])
        for key, spec in self.small['materials'].items():
            self.assertEqual(material_spec({'material': key}, house), spec)
        self.assertEqual(len(house['lights']), len(self.main['lights']) + len(self.small['lights']))
        self.assertEqual(set(house['selection']['house_replaced_ceiling_rooms']), {2, 3, 7})
        self.assertEqual({tuple(p['room_numbers']) for p in house['render_profile_sources']}, {(7,), (2, 3)})
        for original in self.small['lights']:
            imported = next(light for light in house['lights'] if light['name'].endswith('__' + original['name']))
            for field in ('position_mm', 'target_mm'):
                expected = to_canonical_m([n / 1000 for n in original[field]], self.small['frame'])
                actual = to_canonical_m([n / 1000 for n in imported[field]], house['frame'])
                np.testing.assert_allclose(actual, expected, atol=1e-12)
            # All authored room lights are below the 2.60 m suspended ceiling.
            self.assertLess(original['position_mm'][2], 2600)

    def test_procedural_grain_and_veins_keep_small_room_coordinates_in_house_frame(self):
        house = load_configuration(DEFAULT_CONFIG, scope='house')
        canonical_point = [17.4, 4.25, 1.7]
        render_point = np.asarray(to_local_m(canonical_point, house['frame']))
        expected = to_local_m(canonical_point, self.small['frame'])
        transform = shader_coordinate_transform(house['frame'], self.small['frame'])
        actual = np.asarray(transform['rows']) @ render_point + transform['offset_m']
        np.testing.assert_allclose(actual, expected, atol=1e-12)
        for group in ('wood_shaders', 'marble_shaders'):
            for key in self.small[group]:
                self.assertEqual(house[group][key]['coordinate_transform'], transform)

    def test_house_render_can_start_with_either_room_profile_without_losing_main_marble(self):
        house = load_configuration(SMALL_CONFIG, scope='house')
        main_stone = house['materials']['bathroom_tile_marble']
        self.assertEqual(house['marble_shaders'][main_stone['marble_shader']]['vein_ramp'],
                         self.main['marble_shader']['vein_ramp'])
        self.assertEqual(len(house['lights']), len(self.main['lights']) + len(self.small['lights']))

    def test_registry_cannot_escape_module_or_silently_overwrite_optical_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / 'model.yaml'
            registry.write_text('render_profiles: [../outside.yaml]\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'inside the interior module'):
                load_configuration(DEFAULT_CONFIG, scope='house', registry_path=registry)
            conflict = copy.deepcopy(self.small)
            conflict['materials']['bathroom_ceramic'] = {'color_srgb': [0, 0, 0]}
            (root / 'conflict.yaml').write_text(yaml.safe_dump(conflict), encoding='utf-8')
            registry.write_text('render_profiles: [conflict.yaml]\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Conflicting authored render material'):
                load_configuration(DEFAULT_CONFIG, scope='house', registry_path=registry)


if __name__ == '__main__':
    unittest.main()
