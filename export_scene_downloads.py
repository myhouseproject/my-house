#!/usr/bin/env python3
"""Export local building variants and the separate georeferenced exterior scene."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
import trimesh
from project_config import cached_input_path

ROOT = Path(__file__).resolve().parent
Y_UP = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)
ALWAYS_EXCLUDED = {'sufity', 'dom_geo', 'lica_wykonczenia'}
EXTERIOR_CATEGORIES = {
    'dach', 'strop', 'elewacja', 'daszek', 'teren', 'nawierzchnie', 'schody',
    'teren_rzeczywisty', 'ortofoto', 'granica_dzialki', 'budynki_otoczenia', 'drzewa',
}


VARIANTS = {'shell', 'blocks', 'visual'}


def includes_part(part, exterior, variant='visual'):
    if variant not in VARIANTS:
        raise ValueError(f'Nieznany wariant wnętrza: {variant}')
    if variant == 'visual' and part.get('superseded_by_finish'):
        return False
    category = part['category']
    if category == 'wnetrze_bloki' and variant != 'blocks':
        return False
    if category == 'wnetrze_elementy' and variant != 'visual':
        return False
    return category not in ALWAYS_EXCLUDED and (
        exterior or (category not in EXTERIOR_CATEGORIES and not category.startswith('ogrod_')))


def interior_texture(part, vertices, faces, images):
    """Read a declared local image and its surface mapping, never remote URLs."""
    filename = part.get('texture_url')
    if not isinstance(filename, str) or not filename or '\\' in filename or ':' in filename:
        raise ValueError(f"Nieprawidłowa lokalna tekstura dla {part['name']}: {filename!r}")
    relative = Path(filename)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError(f"Tekstura musi należeć do projektu: {filename}")
    root = ROOT.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(f"Brak lokalnej tekstury projektu: {filename}")
    uv = np.asarray(part.get('texture_uv'), dtype=float)
    if uv.shape != (len(vertices), 2) or not np.isfinite(uv).all():
        raise ValueError(f"Nieprawidłowe współrzędne tekstury dla {part['name']}")
    indices = part.get('texture_faces', list(range(len(faces))))
    if not isinstance(indices, list) or not indices or any(
        not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(faces)
        for index in indices
    ) or len(set(indices)) != len(indices):
        raise ValueError(f"Nieprawidłowe ściany tekstury dla {part['name']}")
    if filename not in images:
        with Image.open(path) as image:
            images[filename] = image.copy()
    return images[filename], uv, np.asarray(indices, dtype=np.int64)


def build_download_scene(source, exterior, ortho_image=None, variant='visual'):
    if source.get('units') != 'm' or source.get('up_axis') != 'Z':
        raise ValueError('Eksport wymaga sceny w metrach z osią Z do góry.')
    if not exterior and source.get('coordinate_frame') == 'georeferenced':
        raise ValueError('Eksport wnętrza wymaga scena_lokalna.json; mapa może zawierać skalowanie.')
    scene = trimesh.Scene(base_frame='DOM')
    scene.metadata = {
        'units': 'm', 'up_axis': 'Y',
        'source': 'scena_modelu.json' if exterior else 'scena_lokalna.json',
        'coordinate_frame': source.get('coordinate_frame', 'unspecified'),
        'coordinate_transform': 'glTF (x,y,z) = scene (x,z,-y), metres; no scale added by exporter',
        'model_status': 'working reconstruction; see CZYTAJ_MNIE.md',
        'not_as_built': True,
        'variant': ('exterior_with_garden_and_context_' if exterior else 'interior_without_roof_') + variant,
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
    materials, images = {}, {}
    for part in source['parts']:
        if not includes_part(part, exterior, variant) or part['name'] in duplicate_terrain:
            continue
        vertices = np.asarray(part['positions_m'], dtype=float)
        faces = np.asarray(part['faces'], dtype=np.int64)
        if not len(vertices) or not len(faces):
            continue
        ortho_textured = ortho_image is not None and (
            part['category'] == 'ortofoto' or part.get('use_ortho_texture', False))
        uv = None
        if ortho_textured:
            explicit_uv = part.get('texture_uv')
            if explicit_uv is not None and len(explicit_uv) == len(vertices):
                uv = np.asarray(explicit_uv, dtype=float)
            elif ortho is not None:
                uv = (vertices[:, :2] - ortho_min) / ortho_span
            else:
                raise ValueError(f"Brak współrzędnych tekstury dla {part['name']}")
        groups = [(part['name'], faces, ortho_image if ortho_textured else None,
                   uv, '__orthophoto__' if ortho_textured else None)]
        local_texture = part.get('texture_url') is not None and not ortho_textured
        if local_texture:
            image, uv, indices = interior_texture(part, vertices, faces, images)
            untextured = np.ones(len(faces), dtype=bool)
            untextured[indices] = False
            groups = []
            if untextured.any():
                groups.append((part['name'], faces[untextured], None, None, None))
            texture_name = part['name'] + '__texture' if groups else part['name']
            groups.append((texture_name, faces[indices], image, uv, part['texture_url']))
        for name, surface_faces, image, surface_uv, texture_key in groups:
            rgba = np.clip(np.round(np.asarray(part['color'], dtype=float) * 255), 0, 255).astype(np.uint8)
            if image is not None:
                rgba = np.array([255, 255, 255, 255 if ortho_textured else rgba[3]], dtype=np.uint8)
            material_name = part.get('material', part['category'])
            if local_texture and image is not None:
                material_name += '__texture'
            pbr = {'metallicFactor': 0.0, 'roughnessFactor': 0.82,
                   'alphaMode': 'BLEND' if rgba[3] < 255 else 'OPAQUE', 'doubleSided': True}
            for source_key, gltf_key in (('metallic', 'metallicFactor'),
                                         ('roughness', 'roughnessFactor'),
                                         ('emissive', 'emissiveFactor'),
                                         ('alphaMode', 'alphaMode'),
                                         ('alphaCutoff', 'alphaCutoff'),
                                         ('doubleSided', 'doubleSided')):
                if source_key in part.get('pbr', {}):
                    pbr[gltf_key] = part['pbr'][source_key]
            material_key = (material_name, tuple(rgba), texture_key, json.dumps(pbr, sort_keys=True))
            if material_key not in materials:
                materials[material_key] = trimesh.visual.material.PBRMaterial(
                    name=material_name, baseColorFactor=rgba, **pbr, baseColorTexture=image,
                )
            mesh = trimesh.Trimesh(vertices=vertices, faces=surface_faces, process=False)
            mesh.visual = trimesh.visual.TextureVisuals(uv=surface_uv, material=materials[material_key])
            mesh.unmerge_vertices()  # Flat normals keep walls and roof corners crisp.
            mesh.apply_transform(Y_UP)
            mesh.vertex_normals = np.repeat(mesh.face_normals, 3, axis=0)
            metadata = {k: v for k, v in part.items()
                        if k not in {'positions_m', 'faces', 'texture_uv', 'texture_faces', 'bbox_mm', 'color'}
                        and v is not None}
            if local_texture:
                metadata.update(source_part=part['name'], texture_surface=image is not None)
            mesh.metadata.update(metadata)
            scene.add_geometry(mesh, node_name=name, geom_name=name, metadata=metadata)
    return scene


def export_downloads(local_source, map_source, output_dir, image_path=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ortho_image = None
    if map_source is not None and image_path and Path(image_path).exists():
        with Image.open(image_path) as image:
            ortho_image = image.copy()
    exports = [
        ('dom_wnetrze.glb', local_source, False, 'visual'),
        ('dom_wnetrze_bloki.glb', local_source, False, 'blocks'),
        ('dom_powloka.glb', local_source, False, 'shell'),
    ]
    if map_source is not None:
        exports.append(('dom_bryla.glb', map_source, True, 'visual'))
    for filename, source, exterior, variant in exports:
        scene = build_download_scene(source, exterior, ortho_image, variant)
        payload = trimesh.exchange.gltf.export_glb(scene, include_normals=True)
        (output_dir / filename).write_bytes(payload)
        print(f'Zapisano {filename}: {len(scene.geometry)} obiektów, {len(payload):,} bajtów.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--local-only', action='store_true')
    args = parser.parse_args()
    local_source = json.loads((args.source_dir / 'scena_lokalna.json').read_text(encoding='utf-8'))
    map_source = None if args.local_only else json.loads((args.source_dir / 'scena_modelu.json').read_text(encoding='utf-8'))
    export_downloads(local_source, map_source, args.output_dir, cached_input_path(args.source_dir, 'geoportal_ortho.jpg'))


if __name__ == '__main__':
    main()
