import copy
import io
import json
import struct
import unittest

import numpy as np
from PIL import Image
import trimesh

from export_scene_downloads import build_download_scene


class SceneDownloadRegression(unittest.TestCase):
    def setUp(self):
        prototype = {
            'positions_m': [[11, -30, 1], [12, -30, 1], [11, -29, 2]],
            'faces': [[0, 1, 2]], 'material': 'test', 'color': [0.2, 0.4, 0.6, 0.5],
            'source': 'source drawing', 'note': 'retained description',
        }
        parts = []
        for category in ('sciany', 'dach', 'ogrod_rosliny', 'sufity', 'ortofoto', 'teren_rzeczywisty'):
            part = copy.deepcopy(prototype)
            part.update(name=category, category=category)
            if category == 'ortofoto':
                part['texture_uv'] = [[0, 0], [1, 0], [0, 1]]
            parts.append(part)
        self.source = {'units': 'm', 'up_axis': 'Z', 'parts': parts,
                       'geo_alignment': {'test': 'preserved'}}

    def test_variants_preserve_coordinates_and_metadata(self):
        interior = build_download_scene(self.source, exterior=False)
        self.assertEqual(set(interior.geometry), {'sciany'})
        np.testing.assert_allclose(interior.geometry['sciany'].vertices,
                                   [[11, 1, 30], [12, 1, 30], [11, 2, 29]])
        exterior = build_download_scene(self.source, exterior=True,
                                        ortho_image=Image.new('RGB', (2, 2), 'green'))
        self.assertEqual(set(exterior.geometry), {'sciany', 'dach', 'ogrod_rosliny', 'ortofoto'})
        self.assertEqual(exterior.metadata['duplicate_terrain_omitted'], ['teren_rzeczywisty'])
        for mesh in exterior.geometry.values():
            np.testing.assert_allclose(mesh.vertex_normals, np.repeat(mesh.face_normals, 3, axis=0))
        payload = trimesh.exchange.gltf.export_glb(exterior, include_normals=True)
        json_length, = struct.unpack_from('<I', payload, 12)
        gltf = json.loads(payload[20:20 + json_length])
        material = next(m for m in gltf['materials'] if m['alphaMode'] == 'BLEND')
        self.assertEqual(material['pbrMetallicRoughness']['metallicFactor'], 0)
        self.assertEqual(material['pbrMetallicRoughness']['roughnessFactor'], 0.82)
        self.assertTrue(material['doubleSided'])
        self.assertTrue(gltf.get('images'))
        wall = next(n for n in gltf['nodes'] if n['name'] == 'sciany')
        self.assertEqual(wall['extras']['note'], 'retained description')
        self.assertEqual(wall['extras']['source'], 'source drawing')
        self.assertNotIn('positions_m', wall['extras'])
        self.assertTrue(all('NORMAL' in p['attributes'] for m in gltf['meshes'] for p in m['primitives']))
        reloaded = trimesh.load(io.BytesIO(payload), file_type='glb', force='scene')
        np.testing.assert_allclose(reloaded.bounds, exterior.bounds, atol=1e-6)

    def test_keeps_terrain_when_ortho_geometry_differs(self):
        terrain = next(p for p in self.source['parts'] if p['category'] == 'teren_rzeczywisty')
        terrain['positions_m'][0][2] -= 0.01
        exterior = build_download_scene(self.source, exterior=True)
        self.assertIn('teren_rzeczywisty', exterior.geometry)


if __name__ == '__main__':
    unittest.main()
