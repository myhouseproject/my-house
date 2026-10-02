"""Regression tests for publication isolation, truthful reporting and release rollback."""
from pathlib import Path
import json
import tempfile
import unittest

from scripts.build import select_release, source_manifest, stage_sources
from scripts.build_reports import inspect_scene, write_reports
from scripts.package_site import package_site


class BuildPipelineTests(unittest.TestCase):
    def test_missing_variant_exports_cannot_be_a_valid_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, 'Required exports are missing'):
                write_reports(temporary, 'interior')

    def test_mesh_report_rejects_nonfinite_and_out_of_range_indices(self):
        fixtures = [([[0, 0, 0], [1, 0, 0], [0, 1, float('nan')]], [[0, 1, 2]]),
                    ([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]])]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'scene.json'
            for positions, faces in fixtures:
                path.write_text(json.dumps({'units': 'm', 'up_axis': 'Z', 'parts': [
                    {'name': 'broken', 'positions_m': positions, 'faces': faces}]}))
                report, records = inspect_scene(path)
                self.assertTrue(report['errors'])
                self.assertEqual(records, [])

    def test_open_surface_is_counted_honestly_without_solid_volume(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'scene.json'
            path.write_text(json.dumps({'units': 'm', 'up_axis': 'Z', 'parts': [
                {'name': 'floor', 'category': 'floor', 'positions_m': [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
                 'faces': [[0, 1, 2]]}]}))
            report, records = inspect_scene(path)
            self.assertEqual(report['parts_total'], 1)
            self.assertEqual(report['open_surface_parts'], 1)
            self.assertEqual(report['errors'], [])
            self.assertIsNone(records[0]['enclosed_mesh_volume_m3'])

    def test_publication_excludes_sources_and_obsolete_google_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, target = root / 'release', root / 'site'
            (source / 'google_models').mkdir(parents=True)
            for name in ['index.html', 'dom_wnetrze.glb', 'secret.pdf', 'project.yaml', 'dom_model_CAD.step']:
                (source / name).write_text(name)
            (source / 'google_models/current.glb').write_text('current')
            (source / 'google_models/obsolete.glb').write_text('obsolete')
            (source / 'google_model_georef.json').write_text(json.dumps({
                'model_url': 'google_models/current.glb',
                'invalid': 'google_models/../../secret.pdf'}))
            package_site(source, target)
            self.assertTrue((target / 'google_models/current.glb').is_file())
            for name in ['secret.pdf', 'project.yaml', 'dom_model_CAD.step', 'google_models/obsolete.glb']:
                self.assertFalse((target / name).exists(), name)

    def test_source_manifest_binds_local_edits_and_excludes_build_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'project.yaml').write_text('version: 1')
            (root / 'scena_modelu.json').write_text('stale generated scene')
            (root / 'dom_bryla.glb').write_text('stale generated GLB')
            first = source_manifest(root)
            self.assertNotIn('scena_modelu.json', first['inputs'])
            (root / 'build').mkdir()
            (root / 'build/generated.json').write_text('regeneration')
            self.assertEqual(first['source_sha256'], source_manifest(root)['source_sha256'])
            (root / 'project.yaml').write_text('version: 2')
            self.assertNotEqual(first['config_sha256'], source_manifest(root)['config_sha256'])
            (root / 'stage').mkdir()
            stage_sources(root, root / 'stage', source_manifest(root)['inputs'])
            self.assertFalse((root / 'stage/dom_bryla.glb').exists())

    def test_release_selection_preserves_previous_until_switch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous, candidate = root / 'previous', root / 'candidate'
            previous.mkdir()
            candidate.mkdir()
            (previous / 'manifest.json').write_text('old-complete')
            current = root / 'current'
            select_release(current, previous)
            self.assertEqual((current / 'manifest.json').read_text(), 'old-complete')
            # Candidate is not selected until all checks and final manifest are complete.
            (candidate / 'manifest.json').write_text('new-complete')
            self.assertEqual((current / 'manifest.json').read_text(), 'old-complete')
            select_release(current, candidate)
            self.assertEqual((current / 'manifest.json').read_text(), 'new-complete')
            self.assertTrue((previous / 'manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
