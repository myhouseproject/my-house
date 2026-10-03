"""Run with: python tests/test_viewer_build.py."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ViewerBuildTest(unittest.TestCase):
    def test_hosted_and_portable_outputs_preserve_scene_and_share_georeference(self):
        scene = {'parts': [{'name': 'Żółta ściana </script>', 'color': [0.8, 0.7, 0.4, 1]}]}
        georef = {
            'center': {'lat': 50.85, 'lng': 19.08, 'altitude': 253.7},
            'orientation': {'heading': 0, 'tilt': 0, 'roll': 0},
            'altitude_mode': 'absolute', 'model_url': 'dom_Gruszowa60.glb',
            'camera': {'center': {'lat': 50.85, 'lng': 19.08, 'altitude': 269},
                       'heading': 27, 'tilt': 65, 'range': 110},
        }
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='viewer-build-test-') as directory:
            output = Path(directory)
            for name in ['aktualizuj_podglad.py', 'podglad_szablon.html', 'project_config.py', 'viewer_capture.js']:
                shutil.copyfile(ROOT / name, output / name)
            house_module = output / 'modules' / '03_house_2d'
            house_module.mkdir(parents=True)
            (house_module / 'model.yaml').write_text(json.dumps({
                'schema_version': 1,
                'module': 'house_2d',
                'source_data': {'rooms': []},
                'roof': {},
                'windows': [],
                'external_joinery': []
            }), encoding='utf-8')
            fixtures = {'scena_modelu.json': scene, 'google_model_georef.json': georef}
            for name, data in fixtures.items():
                (output / name).write_text(json.dumps(data), encoding='utf-8')
            for name in ['dom_wnetrze.glb', 'dom_bryla.glb']:
                (output / name).write_bytes(b'glTF-download-fixture')
            subprocess.run([sys.executable, str(output / 'aktualizuj_podglad.py')],
                           check=True, capture_output=True, text=True)
            hosted = (output / 'index.html').read_text(encoding='utf-8')
            portable = (output / 'podglad_3d.html').read_text(encoding='utf-8')
            self.assertIn("const GLB_INTERIOR='';", hosted)
            self.assertIn("const GLB_EXTERIOR='';", hosted)
            self.assertNotIn("const GLB_INTERIOR='';", portable)
            self.assertNotIn("const GLB_EXTERIOR='';", portable)
            for html in [hosted, portable]:
                embedded_scene = html.split('const SCENE=', 1)[1].split(';\nconst GLB_INTERIOR=', 1)[0]
                embedded_georef = html.split('const GOOGLE_MODEL_GEOREF=', 1)[1].split(';\n', 1)[0]
                self.assertEqual(json.loads(embedded_scene), scene)
                self.assertEqual(json.loads(embedded_georef), georef)
                self.assertNotIn('</script>', embedded_scene)
                self.assertNotIn('\n', embedded_scene)
                for marker in ['__GOOGLE_', '__GLB_', '__SCENE__', '__ROOM_LABELS__', '__ORTHO_JPG__', '__CAPTURE_SCRIPT__']:
                    self.assertNotIn(marker, html)
                self.assertIn('https://www.google.com/maps/@50.85,19.08,', html)
                self.assertIn('https://earth.google.com/web/@50.85,19.08,', html)


    def test_interior_only_build_uses_local_rooms_and_declarative_dimensions(self):
        room = {'id': 'R01', 'number': 1, 'name': 'Test', 'reported_area_m2': 6,
                'floor_reference_polygon_mm': [[0, 0], [3000, 0], [3000, 2000], [0, 2000]]}
        local = {'coordinate_frame': 'building_local', 'parts': [{'name': 'wall', 'room_number': 1}]}
        with tempfile.TemporaryDirectory(dir=ROOT.parent, prefix='viewer-local-test-') as directory:
            output = Path(directory)
            for name in ['aktualizuj_podglad.py', 'podglad_szablon.html', 'project_config.py', 'viewer_capture.js']:
                shutil.copyfile(ROOT / name, output / name)
            for module, model in [
                ('03_house_2d', {'schema_version': 1, 'module': 'house_2d', 'source_data': {'rooms': [room]}}),
                ('04_house_3d', {'schema_version': 1, 'module': 'house_3d', 'parameters': {'parapet_top_mm': 5150}}),
                ('06_interior', {'schema_version': 1, 'module': 'interior', 'viewer_navigation': {'eye_height_m': 1.65}, 'viewer_presets': {'bathroom': {'room_id': 'R01', 'entrance_side': 'north'}}, 'room_policies': {'R01': {
                    'floor': {'level_parameter': 'finished_floor_level_mm', 'override_level_mm': 125, 'status': 'assumed'},
                    'ceiling': {'level_parameter': 'ceiling_level_mm', 'override_level_mm': 2725, 'status': 'assumed'},
                }}}),
            ]:
                folder = output / 'modules' / module
                folder.mkdir(parents=True)
                (folder / 'model.yaml').write_text(json.dumps(model), encoding='utf-8')
            (output / 'scena_lokalna.json').write_text(json.dumps(local), encoding='utf-8')
            (output / 'dom_powloka.glb').write_bytes(b'local-shell')
            (output / 'data').mkdir()
            cache = {'alignment': {'house_calibration': {'model_to_geo_local_affine_mm': [[2, 0, 10000], [0, 2, 20000]]}}}
            (output / 'data/geoportal_teren.json').write_text(json.dumps(cache), encoding='utf-8')
            (output / 'data/geoportal_ortho.jpg').write_bytes(b'ortho-cache')
            subprocess.run([sys.executable, str(output / 'aktualizuj_podglad.py')], check=True, capture_output=True)
            hosted = (output / 'index.html').read_text(encoding='utf-8')
            config = json.loads(hosted.split('const VIEWER_CONFIG=', 1)[1].split(';\n', 1)[0])
            rooms = json.loads(hosted.split('const ROOM_LABELS=', 1)[1].split(';\n', 1)[0])
            self.assertEqual(config['bounds_m'], {'minx': 0, 'maxx': 3, 'miny': 0, 'maxy': 2})
            self.assertEqual(config['parameters']['parapet_top_mm'], 5150)
            self.assertEqual(config['room_presets']['bathroom'], {'room_id': 'R01', 'entrance_side': 'north'})
            self.assertEqual(config['navigation']['eye_height_m'], 1.65)
            self.assertEqual(config['footprint_m'], [[0, 0], [3, 0], [3, 2], [0, 2]])
            self.assertFalse(config['map_scene_available'])
            self.assertFalse(config['google_available'])
            self.assertTrue(config['local_scene_available'])
            self.assertEqual(rooms[0]['polygon_m'], [[0, 0], [3, 0], [3, 2], [0, 2]])
            self.assertEqual(rooms[0]['local_x'], 1.5)
            self.assertEqual(rooms[0]['x'], 13)  # map affine comes from data/, never rescales local x
            self.assertEqual(rooms[0]['policy']['floor']['level_mm'], 125)
            self.assertEqual(rooms[0]['policy']['ceiling']['level_mm'], 2725)
            self.assertIn("const ORTHO_JPG='b3J0aG8tY2FjaGU=';", hosted)
            # A fresh stage cache wins over the checkout's downloaded cache.
            cache['alignment']['house_calibration']['model_to_geo_local_affine_mm'][0][2] = 30000
            (output / 'geoportal_teren.json').write_text(json.dumps(cache), encoding='utf-8')
            subprocess.run([sys.executable, str(output / 'aktualizuj_podglad.py')], check=True, capture_output=True)
            rebuilt = (output / 'index.html').read_text(encoding='utf-8')
            rebuilt_rooms = json.loads(rebuilt.split('const ROOM_LABELS=', 1)[1].split(';\n', 1)[0])
            self.assertEqual(rebuilt_rooms[0]['x'], 33)
            self.assertEqual(rebuilt_rooms[0]['local_x'], 1.5)
            portable = (output / 'podglad_3d.html').read_text(encoding='utf-8')
            self.assertIn("const GLB_SHELL='bG9jYWwtc2hlbGw=';", portable)
            self.assertIn("const GLB_SHELL='';", hosted)


if __name__ == '__main__':
    unittest.main()
