"""KMZ bytes and COLLADA references must survive repeated exports exactly."""
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
import zipfile

import collada
import numpy as np
import trimesh

import eksportuj_google_earth as exporter


class GoogleReproducibilityTests(unittest.TestCase):
    def test_kmz_is_identical_and_collada_ids_resolve_after_two_exports(self):
        meshes = [trimesh.creation.box(extents=[1, 2, 3]),
                  trimesh.creation.box(extents=[2, 3, 4])]
        meshes[1].apply_translation([4, 5, 6])
        frame = SimpleNamespace(lon=19.0, lat=50.0, google_elevation=250.0,
                                wgs84=lambda xy: np.asarray(xy) * 1e-5 + [19.0, 50.0])
        scene = {'parts': [{'category': 'sciany', 'color': [1, .5, .2, 1],
                           'positions_m': mesh.vertices.tolist(), 'faces': mesh.faces.tolist()}
                          for mesh in meshes]}
        with tempfile.TemporaryDirectory() as temporary, patch.object(exporter, 'ROOT', Path(temporary)):
            path = Path(temporary) / 'dom_Gruszowa60.kmz'
            exporter.write_kmz(scene, {'parts': []}, frame, meshes)
            first = path.read_bytes()
            exporter.write_kmz(scene, {'parts': []}, frame, meshes)
            self.assertEqual(first, path.read_bytes())
            with zipfile.ZipFile(io.BytesIO(first)) as archive:
                data = archive.read('models/model.dae')
            xml = ET.fromstring(data)
            ids = [node.get('id') for node in xml.iter() if node.get('id')]
            self.assertEqual(len(ids), len(set(ids)), 'COLLADA IDs must be globally unique')
            for node in xml.iter():
                for key in ['source', 'target', 'url']:
                    value = node.get(key, '')
                    if value.startswith('#'):
                        self.assertIn(value[1:], ids)
            loaded = collada.Collada(io.BytesIO(data))
            self.assertEqual(len(loaded.geometries), len(meshes))
            for actual, expected in zip(loaded.geometries, meshes):
                primitive = actual.primitives[0]
                self.assertEqual(len(primitive), len(expected.faces))
                np.testing.assert_allclose(primitive.vertex.min(axis=0), expected.bounds[0])
                np.testing.assert_allclose(primitive.vertex.max(axis=0), expected.bounds[1])


if __name__ == '__main__':
    unittest.main()
