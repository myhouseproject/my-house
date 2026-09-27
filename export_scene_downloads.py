#!/usr/bin/env python3
"""Export the current, georeferenced scene to the portal's downloadable GLBs."""
import json
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh

ROOT = Path(__file__).resolve().parent
Y_UP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)
ALWAYS_EXCLUDED = {'sufity', 'dom_geo'}
EXTERIOR_CATEGORIES = {
    'dach', 'strop', 'elewacja', 'daszek', 'teren', 'nawierzchnie', 'schody',
    'teren_rzeczywisty', 'ortofoto', 'granica_dzialki', 'budynki_otoczenia', 'drzewa',
}


def includes_part(part, exterior):
    category = part['category']
    return category not in ALWAYS_EXCLUDED and (
        exterior or (category not in EXTERIOR_CATEGORIES and not category.startswith('ogrod_')))


def build_download_scene(source, exterior, ortho_image=None):
    if source.get('units') != 'm' or source.get('up_axis') != 'Z':
        raise ValueError('Eksport wymaga sceny w metrach z osią Z do góry.')
    scene = trimesh.Scene(base_frame='DOM')
    scene.metadata = {
        'units': 'm', 'up_axis': 'Y', 'source': 'scena_modelu.json',
        'coordinate_transform': 'glTF (x,y,z) = scene (x,z,-y), metres; georeference already applied',
        'model_status': 'working reconstruction; see CZYTAJ_MNIE.md',
        'not_as_built': True,
        'variant': 'exterior_with_garden_and_context' if exterior else 'interior_without_roof',
        'geo_alignment': source.get('geo_alignment', {}),
        'geo_validation': source.get('geo_validation', {}),
    }
    ortho = next((p for p in source['parts'] if p['category'] == 'ortofoto'), None)
    if ortho is not None:
        ortho_xy = np.asarray(ortho['positions_m'], dtype=float)[:, :2]
        ortho_min = ortho_xy.min(axis=0)
        ortho_span = np.maximum(ortho_xy.max(axis=0) - ortho_min, 1e-9)
    duplicate_terrain = {
        p['name'] for p in source['parts']
        if ortho is not None and p['category'] == 'teren_rzeczywisty'
        and p['positions_m'] == ortho['positions_m'] and p['faces'] == ortho['faces']
    }
    # glTF has no polygon-offset setting. The ortho mesh already contains the
    # same terrain surface; exporting it twice would cause depth flickering.
    scene.metadata['duplicate_terrain_omitted'] = sorted(duplicate_terrain) if exterior else []
    materials = {}
    for part in source['parts']:
        if not includes_part(part, exterior) or part['name'] in duplicate_terrain:
            continue
        vertices = np.asarray(part['positions_m'], dtype=float)
        faces = np.asarray(part['faces'], dtype=np.int64)
        if not len(vertices) or not len(faces):
            continue
        textured = ortho_image is not None and (
            part['category'] == 'ortofoto' or part.get('use_ortho_texture', False))
        rgba = np.clip(np.round(np.asarray(part['color'], dtype=float) * 255), 0, 255).astype(np.uint8)
        if textured:
            rgba = np.array([255, 255, 255, 255], dtype=np.uint8)
        material_name = part.get('material', part['category'])
        material_key = (material_name, tuple(rgba), textured)
        if material_key not in materials:
            materials[material_key] = trimesh.visual.material.PBRMaterial(
                name=material_name, baseColorFactor=rgba, metallicFactor=0.0,
                roughnessFactor=0.82,
                alphaMode='BLEND' if rgba[3] < 255 else 'OPAQUE',
                doubleSided=True, baseColorTexture=ortho_image if textured else None,
            )
        uv = None
        if textured:
            explicit_uv = part.get('texture_uv')
            if explicit_uv is not None and len(explicit_uv) == len(vertices):
                uv = np.asarray(explicit_uv, dtype=float)
            elif ortho is not None:
                uv = (vertices[:, :2] - ortho_min) / ortho_span
            else:
                raise ValueError(f"Brak współrzędnych tekstury dla {part['name']}")
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=materials[material_key])
        mesh.unmerge_vertices()  # Flat normals keep walls and roof corners crisp.
        mesh.apply_transform(Y_UP)
        mesh.vertex_normals = np.repeat(mesh.face_normals, 3, axis=0)
        metadata = {k: v for k, v in part.items()
                    if k not in {'positions_m', 'faces', 'texture_uv', 'bbox_mm', 'color'} and v is not None}
        scene.add_geometry(mesh, node_name=part['name'], geom_name=part['name'], metadata=metadata)
    return scene


def main():
    source = json.loads((ROOT / 'scena_modelu.json').read_text(encoding='utf-8'))
    image_path = ROOT / 'geoportal_ortho.jpg'
    ortho_image = None
    if image_path.exists():
        with Image.open(image_path) as image:
            ortho_image = image.copy()
    for filename, exterior in (('dom_wnetrze.glb', False), ('dom_bryla.glb', True)):
        scene = build_download_scene(source, exterior, ortho_image)
        payload = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
        (ROOT / filename).write_bytes(payload)
        print(f'Zapisano {filename}: {len(scene.geometry)} obiektów, {len(payload):,} bajtów.')


if __name__ == '__main__':
    main()
