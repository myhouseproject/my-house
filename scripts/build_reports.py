"""Checks of actual mesh artefacts, separate from architectural acceptance."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def inspect_scene(path):
    """Reject malformed meshes; report open surfaces without inventing solid validity."""
    scene = json.loads(Path(path).read_text(encoding='utf-8'))
    errors, records, signatures = [], [], defaultdict(list)
    if scene.get('units') != 'm' or scene.get('up_axis') != 'Z':
        errors.append('Scene must use metres, Z-up.')
    parts = scene.get('parts', [])
    if not parts:
        errors.append('Scene has no parts.')
    names = Counter(part.get('name') for part in parts)
    errors.extend(f'Duplicate name: {name}' for name, count in names.items() if count > 1)
    for part in parts:
        name = part.get('name', '<unnamed>')
        try:
            vertices = np.asarray(part['positions_m'], dtype=float)
            raw_faces = np.asarray(part['faces'])
            if vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices):
                raise ValueError('vertices must be a non-empty Nx3 array')
            if not np.isfinite(vertices).all():
                raise ValueError('non-finite vertex coordinate')
            if raw_faces.ndim != 2 or raw_faces.shape[1] != 3 or not len(raw_faces):
                raise ValueError('faces must be a non-empty Nx3 array')
            faces = raw_faces.astype(np.int64)
            if not np.array_equal(faces, raw_faces):
                raise ValueError('face indices must be integers')
            if faces.min() < 0 or faces.max() >= len(vertices):
                raise ValueError('face index outside vertex array')
            mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
            degenerate = int(np.count_nonzero(mesh.area_faces <= 1e-14))
            # Degeneracy is reported; historical surface layers can contain seams.
            rec = {key: value for key, value in part.items()
                   if key not in {'positions_m', 'faces', 'texture_uv', 'bbox_mm'}}
            rec.update(vertex_count=len(vertices), triangle_count=len(faces),
                       bounds_m=mesh.bounds.tolist(),
                       watertight=bool(mesh.is_watertight),
                       winding_consistent=bool(mesh.is_winding_consistent),
                       degenerate_triangles=degenerate,
                       surface_area_m2=float(mesh.area),
                       enclosed_mesh_volume_m3=(float(abs(mesh.volume))
                                               if mesh.is_watertight else None))
            records.append(rec)
            # Geometric duplicates, invariant to vertex and face ordering.
            triangles = np.round(vertices[faces], 7)
            triangle_keys = sorted(tuple(sorted(map(tuple, triangle))) for triangle in triangles)
            signature = hashlib.sha256(repr(triangle_keys).encode()).hexdigest()
            signatures[signature].append(name)
        except (KeyError, ValueError, TypeError, IndexError, OverflowError) as exc:
            errors.append(f'{name}: {exc}')
    report = {
        'source_file': Path(path).name, 'source_sha256': sha256(path),
        'coordinate_frame': scene.get('coordinate_frame', 'unspecified'),
        'parts_total': len(parts), 'parts_checked': len(records),
        'vertices_total': sum(r['vertex_count'] for r in records),
        'triangles_total': sum(r['triangle_count'] for r in records),
        'watertight_parts': sum(r['watertight'] for r in records),
        'open_surface_parts': sum(not r['watertight'] for r in records),
        'degenerate_triangles': sum(r['degenerate_triangles'] for r in records),
        'open_declared_solids': [r['name'] for r in records
                                 if r.get('geometry') == 'solid' and not r['watertight']],
        'inconsistent_winding_solids': [r['name'] for r in records
                                         if r.get('geometry') == 'solid' and not r['winding_consistent']],
        'degenerate_parts': [r['name'] for r in records if r['degenerate_triangles']],
        'pending_volume_parts': [r['name'] for r in records
                                 if str(r.get('volume_validation', '')).startswith('pending_')],
        'duplicate_mesh_groups': sorted(v for v in signatures.values() if len(v) > 1),
        'categories': dict(sorted(Counter(r.get('category') for r in records).items())),
        'errors': errors,
    }
    return report, records


def write_reports(directory, scope):
    directory = Path(directory)
    required = ['dom_wnetrze.glb', 'dom_wnetrze_bloki.glb', 'dom_powloka.glb']
    if scope == 'full':
        required += ['dom_bryla.glb', 'dom_Gruszowa60.glb', 'dom_Gruszowa60.kmz',
                     'google_model_georef.json']
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise ValueError('Required exports are missing: ' + ', '.join(missing))
    reports, lists = {}, {}
    for name in ['scena_lokalna.json'] + (['scena_modelu.json'] if scope == 'full' else []):
        reports[name], lists[name] = inspect_scene(directory / name)
        expected_frame = 'building_local' if name == 'scena_lokalna.json' else 'georeferenced'
        if reports[name]['coordinate_frame'] != expected_frame:
            reports[name]['errors'].append(f'{name}: expected coordinate frame {expected_frame}')
        if name == 'scena_lokalna.json':
            for field in ['open_declared_solids', 'inconsistent_winding_solids', 'degenerate_parts']:
                for part_name in reports[name][field]:
                    reports[name]['errors'].append(f'{part_name}: {field}')
            visual_parts = {part['name'] for part in lists[name]
                            if part.get('category') == 'wnetrze_elementy'}
            for group in reports[name]['duplicate_mesh_groups']:
                duplicates = visual_parts.intersection(group)
                if len(duplicates) > 1:
                    reports[name]['errors'].append('Duplicate visual interior geometry: ' + ', '.join(sorted(duplicates)))
    exports = {}
    for path in sorted(directory.glob('*.glb')):
        loaded = trimesh.load(path, force='scene', process=False)
        if not loaded.geometry or not np.isfinite(loaded.bounds).all():
            raise ValueError(f'Empty or invalid GLB export: {path.name}')
        exports[path.name] = {'sha256': sha256(path), 'size_bytes': path.stat().st_size,
                              'mesh_count': len(loaded.geometry),
                              'bounds_m_gltf_y_up': loaded.bounds.tolist()}
    errors = [message for report in reports.values() for message in report['errors']]
    warnings = []
    if scope == 'full':
        for field in ['open_declared_solids', 'inconsistent_winding_solids', 'degenerate_parts', 'pending_volume_parts']:
            warnings.extend(f'{name}: {field}' for name in reports['scena_modelu.json'][field])
    report = {
        'schema_version': 2, 'scope': scope,
        'status': ('failed' if errors else 'mesh_integrity_passed_with_warnings'
                   if warnings else 'mesh_integrity_passed'),
        'meaning': 'Finite indexed triangle meshes and readable exports; not an architectural, '
                   'as-built, collision, structural, or BREP acceptance certificate.',
        'step': {'status': 'archival_not_regenerated', 'included_in_release': False,
                 'reason': 'No exact BREP exporter has been verified for the canonical mesh model.'},
        'scenes': reports, 'exports': exports, 'errors': errors, 'warnings': warnings,
    }
    write_json(directory / 'kontrola_modelu.json', report)
    write_json(directory / 'lista_elementow.json', {
        'schema_version': 2, 'units': 'm', 'scenes': lists,
        'source_sha256': {name: report['source_sha256'] for name, report in reports.items()},
    })
    if errors:
        raise ValueError('Mesh validation failed: ' + '; '.join(errors[:10]))
    return report
