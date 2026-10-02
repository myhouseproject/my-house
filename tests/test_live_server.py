"""Meaningful regression gates for source rebuilds and retaining good output."""
import importlib.util
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('live_server', ROOT / 'serwer_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveBuildTests(unittest.TestCase):
    def wait_for_build(self, coordinator):
        deadline = time.monotonic() + 2
        while coordinator.building and time.monotonic() < deadline:
            time.sleep(.005)
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


if __name__ == '__main__':
    unittest.main()
