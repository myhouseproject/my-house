"""Meaningful regression gates for source rebuilds and retaining good output."""
import importlib.util
from pathlib import Path
import tempfile
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('live_server', ROOT / 'serwer_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveBuildTests(unittest.TestCase):
    def wait_for_build(self, coordinator):
        deadline = time.monotonic() + 5
        while (coordinator.building or coordinator.version == 0) and not coordinator.error and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(coordinator.building)

    def test_yaml_rebuild_changes_version_but_generated_output_does_not_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.yaml'
            source.write_text('version: 1')
            calls, clock = [], [0.]
            def run(command, **kwargs):
                calls.append(command)
                (root / 'build/current').mkdir(parents=True, exist_ok=True)
                (root / 'build/current/index.html').write_text('new artifact')
                return SimpleNamespace(returncode=0)
            coordinator = live.BuildCoordinator(root, runner=run, clock=lambda: clock[0])
            source.write_text('version: 2')
            self.assertFalse(coordinator.poll()['building'])  # debounce source writes
            clock[0] = 1
            coordinator.poll()
            self.wait_for_build(coordinator)
            self.assertGreater(coordinator.version, 0)
            self.assertEqual(calls[0][-2:], ['--scope', 'interior'])
            coordinator.poll()
            self.assertEqual(len(calls), 1)
            (root / 'build/current/index.html').write_text('output-only change')
            clock[0] = 3
            coordinator.poll()
            self.assertEqual(len(calls), 1)

    def test_failed_build_keeps_last_version_and_retries_only_on_new_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'project.yaml'
            source.write_text('valid: true')
            calls, clock = [], [0.]
            def fail(*args, **kwargs):
                calls.append(args)
                return SimpleNamespace(returncode=1, stderr='invalid YAML', stdout='')
            coordinator = live.BuildCoordinator(root, runner=fail, clock=lambda: clock[0])
            coordinator.version = 123
            source.write_text('invalid: [')
            coordinator.poll(); clock[0] = 1; coordinator.poll()
            self.wait_for_build(coordinator)
            self.assertEqual(coordinator.version, 123)
            self.assertEqual(coordinator.error, 'invalid YAML')
            clock[0] = 2; coordinator.poll()
            self.assertEqual(len(calls), 1)
            source.write_text('valid: again')
            coordinator.poll(); clock[0] = 3; coordinator.poll()
            self.wait_for_build(coordinator)
            self.assertEqual(len(calls), 2)


    def test_survey_json_raster_and_source_manifest_each_rebuild_full_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = ['data/geoportal_teren.json', 'data/geoportal_ortho.jpg', 'sources/manifest.yaml']
            for name in inputs:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'original source')
            calls, clock = [], [0.]
            def run(command, **kwargs):
                calls.append(command)
                for name in ['build/current/index.html', 'dist/index.html', 'scena_modelu.json', 'dom_bryla.glb']:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'generated release')
                return SimpleNamespace(returncode=0)
            coordinator = live.BuildCoordinator(root, scope='full', runner=run, clock=lambda: clock[0])
            for index, name in enumerate(inputs, 1):
                with self.subTest(source=name):
                    previous_version = coordinator.version
                    (root / name).write_bytes(b'updated contents')
                    self.assertFalse(coordinator.poll()['building'])
                    clock[0] += 1
                    coordinator.poll()
                    self.wait_for_build(coordinator)
                    self.assertEqual(len(calls), index)
                    self.assertEqual(calls[-1][-2:], ['--scope', 'full'])
                    self.assertGreater(coordinator.version, previous_version)
                    clock[0] += 1
                    coordinator.poll()
                    self.assertEqual(len(calls), index, 'generated artifacts must not trigger another build')

    def test_unchanged_evidence_is_not_rehashed_and_removed_files_leave_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / 'sources/architectural.pdf'
            evidence.parent.mkdir()
            evidence.write_bytes(b'PDF content')
            cache = {}
            first = live.source_fingerprint(root, cache)
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('unchanged evidence was reread')):
                self.assertEqual(live.source_fingerprint(root, cache), first)
            evidence.write_bytes(b'new content')  # same size as prior evidence
            changed = live.source_fingerprint(root, cache)
            self.assertNotEqual(changed, first)
            evidence.unlink()
            self.assertNotEqual(live.source_fingerprint(root, cache), changed)
            self.assertFalse(cache)


if __name__ == '__main__':
    unittest.main()
