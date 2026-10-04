"""Manual render inputs stay data and have bounded output dimensions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_render_job as job


class RenderJobTests(unittest.TestCase):
    def test_camera_validation_precedes_saved_execution_arguments(self):
        camera = {'resolution': [4000, 3000], 'kind': 'dom-render-camera',
                  'note': '$(echo untrusted); `echo not-code`'}
        with tempfile.TemporaryDirectory() as directory, patch.object(job, 'JOB', Path(directory)), \
                patch.object(job.subprocess, 'run') as run:
            args = job.prepare(json.dumps(camera), 'final')
            saved = json.loads((Path(directory) / 'camera.json').read_text())
            self.assertEqual(saved['resolution'], [2000, 1500])
            self.assertEqual(saved['note'], camera['note'])
            self.assertEqual(run.call_args.args[0][-1], '--validate-only')
            self.assertNotIn('shell', run.call_args.kwargs)
            self.assertEqual(args[args.index('--scope') + 1], 'house')
            self.assertEqual(json.loads((Path(directory) / 'arguments.json').read_text()), args)

    def test_rejects_invalid_quality_and_unbounded_input_before_spawn(self):
        with patch.object(job.subprocess, 'run') as run:
            for text, quality in [('{}', '$(bad)'), ('x' * 65537, 'final'),
                                  ('[]', 'preview'), ('{"resolution":[true,2000]}', 'final')]:
                with self.assertRaises(ValueError):
                    job.prepare(text, quality)
            run.assert_not_called()

    def test_preview_reduces_resolution_while_preserving_portrait_aspect(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(job, 'JOB', Path(directory)), \
                patch.object(job.subprocess, 'run'):
            job.prepare('{"resolution":[1040,2000]}', 'preview')
            saved = json.loads((Path(directory) / 'camera.json').read_text())
            self.assertEqual(saved['resolution'], [520, 1000])
            self.assertEqual(saved['aspect_ratio'], .52)

    def test_declared_tile_variant_is_forwarded_and_unknown_choice_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(job, 'JOB', Path(directory)), \
                patch.object(job.subprocess, 'run'):
            args = job.prepare('', 'final', 'cerrad_calacatta_gold')
            self.assertEqual(args[args.index('--tile-variant') + 1], 'cerrad_calacatta_gold')
        with patch.object(job.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'Unknown bathroom tile variant'):
                job.prepare('', 'final', 'invented')
            run.assert_not_called()

    def test_invalid_camera_cannot_produce_execution_arguments(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory, patch.object(job, 'JOB', Path(directory)), \
                patch.object(job.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['validate'])):
            with self.assertRaises(subprocess.CalledProcessError):
                job.prepare('{"resolution":[1000,800],"eye":["invalid",0,0]}', 'preview')
            self.assertFalse((Path(directory) / 'arguments.json').exists())


if __name__ == '__main__':
    unittest.main()
