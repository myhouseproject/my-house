"""Interior images are portable in GLB and map only to declared surfaces."""
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
import trimesh

from export_scene_downloads import build_download_scene


def mural_part(**changes):
    box = trimesh.creation.box(extents=[3.4, .012, 1.1])
    box.apply_translation([25.7, 10.3, 2.2])
    uv = (box.vertices[:, [0, 2]] - box.bounds[0, [0, 2]]) / [3.4, 1.1]
    front = np.flatnonzero(box.face_normals[:, 1] < -.9).tolist()
    return {
        'name': 'FIN_BEDROOM_MURAL', 'category': 'wnetrze_elementy',
        'material': 'bedroom_mural', 'color': [.5, .6, .3, 1],
        'positions_m': box.vertices.tolist(), 'faces': box.faces.tolist(),
        'texture_url': 'assets/textures/mural.png', 'texture_uv': uv.tolist(),
        'texture_faces': front, 'interior_finish': True, **changes,
    }


def source(*parts):
    return {'units': 'm', 'up_axis': 'Z', 'coordinate_frame': 'building_local',
            'parts': list(parts)}


def parse_glb(scene):
    payload = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
    length, kind = struct.unpack_from('<II', payload, 12)
    assert kind == 0x4E4F534A
    document = json.loads(payload[20:20 + length])
    return document, payload[28 + length:]


class InteriorTextureExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        image_path = self.root / 'assets/textures/mural.png'
        image_path.parent.mkdir(parents=True)
        self.pixels = np.array([[[255, 0, 0], [0, 255, 0]],
                                [[0, 0, 255], [255, 255, 0]]], dtype=np.uint8)
        Image.fromarray(self.pixels).save(image_path)
        self.root_patch = patch('export_scene_downloads.ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_glb_embeds_image_without_tint_only_on_front_faces(self):
        part = mural_part()
        scene = build_download_scene(source(part), exterior=False)
        self.assertEqual(set(scene.geometry), {'FIN_BEDROOM_MURAL', 'FIN_BEDROOM_MURAL__texture'})
        plain = scene.geometry['FIN_BEDROOM_MURAL']
        front = scene.geometry['FIN_BEDROOM_MURAL__texture']
        self.assertEqual(len(front.faces), len(part['texture_faces']))
        self.assertEqual(len(plain.faces) + len(front.faces), len(part['faces']))
        self.assertIsNone(plain.visual.material.baseColorTexture)
        np.testing.assert_array_equal(front.visual.material.baseColorFactor, [255] * 4)
        np.testing.assert_array_equal(plain.visual.material.baseColorFactor, [128, 153, 76, 255])
        expected_uv = np.asarray(part['texture_uv'])[
            np.asarray(part['faces'])[part['texture_faces']].ravel()]
        np.testing.assert_allclose(front.visual.uv, expected_uv)

        gltf, binary = parse_glb(scene)
        self.assertEqual(len(gltf['images']), 1)
        embedded = gltf['images'][0]
        self.assertIn('bufferView', embedded)
        self.assertNotIn('uri', embedded)
        view = gltf['bufferViews'][embedded['bufferView']]
        start = view.get('byteOffset', 0)
        with Image.open(io.BytesIO(binary[start:start + view['byteLength']])) as image:
            np.testing.assert_array_equal(np.asarray(image), self.pixels)
        node = next(node for node in gltf['nodes'] if node['name'] == 'FIN_BEDROOM_MURAL__texture')
        self.assertEqual(node['extras']['source_part'], part['name'])
        self.assertTrue(node['extras']['texture_surface'])
        self.assertNotIn('texture_faces', node['extras'])
        primitive = gltf['meshes'][node['mesh']]['primitives'][0]
        material = gltf['materials'][primitive['material']]['pbrMetallicRoughness']
        self.assertEqual(material['baseColorFactor'], [1, 1, 1, 1])
        self.assertIn('baseColorTexture', material)
        accessor = gltf['accessors'][primitive['attributes']['TEXCOORD_0']]
        view = gltf['bufferViews'][accessor['bufferView']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        actual_uv = np.frombuffer(binary, dtype='<f4', count=accessor['count'] * 2,
                                  offset=offset).reshape(-1, 2)
        # glTF measures V down from the image top; the scene contract measures V up.
        expected_uv[:, 1] = 1 - expected_uv[:, 1]
        np.testing.assert_allclose(actual_uv, expected_uv, atol=1e-6)

    def test_nonvisual_variants_do_not_require_interior_images(self):
        part = mural_part(texture_url='assets/missing.jpg')
        for variant in ('shell', 'blocks'):
            with self.subTest(variant=variant):
                scene = build_download_scene(source(part), exterior=False, variant=variant)
                self.assertFalse(scene.geometry)

    def test_rejects_remote_escaping_missing_or_invalid_surface_declarations(self):
        invalid = (
            {'texture_url': 'https://example.org/mural.jpg'},
            {'texture_url': '../mural.png'},
            {'texture_url': '/tmp/mural.png'},
            {'texture_url': 'assets/missing.jpg'},
            {'texture_uv': [[0, 0]]},
            {'texture_uv': [[float('nan'), 0]] * 8},
            {'texture_faces': [100]},
            {'texture_faces': [0, 0]},
            {'texture_faces': [True]},
        )
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                build_download_scene(source(mural_part(**changes)), exterior=False)


if __name__ == '__main__':
    unittest.main()
