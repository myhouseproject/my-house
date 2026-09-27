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
            for name in ['aktualizuj_podglad.py', 'podglad_szablon.html']:
                shutil.copyfile(ROOT / name, output / name)
            fixtures = {'dane_zrodlowe.json': {'rooms': []}, 'scena_modelu.json': scene,
                        'google_model_georef.json': georef}
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
                for marker in ['__GOOGLE_', '__GLB_', '__SCENE__', '__ROOM_LABELS__', '__ORTHO_JPG__']:
                    self.assertNotIn(marker, html)
                self.assertIn('https://www.google.com/maps/@50.85,19.08,', html)
                self.assertIn('https://earth.google.com/web/@50.85,19.08,', html)


if __name__ == '__main__':
    unittest.main()
