"""Download variants and material properties must survive the actual GLB export."""
import json
import struct
import unittest

import numpy as np
import trimesh

from export_scene_downloads import build_download_scene


def part(name, category='wnetrze_elementy', **metadata):
    mesh = trimesh.creation.box(extents=[1, 1, .01])
    mesh.apply_translation([26, 3, -.005])
    return {'name': name, 'category': category, 'material': 'test material',
            'color': [.7, .6, .5, 1], 'positions_m': mesh.vertices.tolist(),
            'faces': mesh.faces.tolist(), **metadata}


def source(*parts):
    return {'units': 'm', 'up_axis': 'Z', 'coordinate_frame': 'building_local',
            'parts': list(parts)}


class SceneDownloadTests(unittest.TestCase):
    def test_finished_floor_replaces_source_only_in_visual_export(self):
        reference = part('reference floor', 'podlogi', superseded_by_finish=True)
        tiles = part('tile floor')
        block = part('layout block', 'wnetrze_bloki')
        model = source(reference, tiles, block)
        original_floor = np.asarray(reference['positions_m']).copy()
        for exterior in (False, True):
            for variant, expected in (
                ('visual', {'tile floor'}),
                ('shell', {'reference floor'}),
                ('blocks', {'reference floor', 'layout block'}),
            ):
                scene = build_download_scene(model, exterior=exterior, variant=variant)
                self.assertEqual(set(scene.geometry), expected)
                floor = scene.geometry['tile floor' if variant == 'visual' else 'reference floor']
                self.assertAlmostEqual(float(floor.bounds[1, 1]), 0, places=9)
        np.testing.assert_array_equal(model['parts'][0]['positions_m'], original_floor)

    def test_binary_glb_preserves_distinct_pbr_properties_and_default_materials(self):
        scene = build_download_scene(source(
            part('brass', pbr={'metallic': .85, 'roughness': .22}),
            part('matte brass', pbr={'metallic': .85, 'roughness': .65}),
            part('lamp', pbr={'roughness': .3, 'emissive': [1, .8, .6]}),
            part('legacy'),
        ), exterior=False)
        binary = trimesh.exchange.gltf.export_glb(scene)
        json_length, chunk_kind = struct.unpack_from('<II', binary, 12)
        self.assertEqual(chunk_kind, 0x4E4F534A)
        gltf = json.loads(binary[20:20+json_length])
        materials = {}
        for node in gltf['nodes']:
            if 'mesh' in node:
                primitive = gltf['meshes'][node['mesh']]['primitives'][0]
                materials[node['name']] = gltf['materials'][primitive['material']]
        self.assertAlmostEqual(materials['brass']['pbrMetallicRoughness']['metallicFactor'], .85)
        self.assertAlmostEqual(materials['brass']['pbrMetallicRoughness']['roughnessFactor'], .22)
        self.assertAlmostEqual(materials['matte brass']['pbrMetallicRoughness']['roughnessFactor'], .65)
        self.assertEqual(materials['lamp']['emissiveFactor'], [1, .8, .6])
        self.assertAlmostEqual(materials['legacy']['pbrMetallicRoughness']['roughnessFactor'], .82)
        self.assertAlmostEqual(materials['legacy']['pbrMetallicRoughness']['metallicFactor'], 0)


if __name__ == '__main__':
    unittest.main()
