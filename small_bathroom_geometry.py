"""Small bathroom and laundry: authored concept geometry in a shared room frame.

Dimensions, material assignments and repetitions are all declared in the YAML.
The generator does not alter architectural walls or infer appliances behind doors.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import box as rectangle
from shapely.ops import unary_union

from bathroom_geometry import vessel_mesh


def build_small_bathroom(configuration, emit):
    if not configuration or not configuration.get('enabled', True):
        return
    cfg = configuration
    frame = cfg['frame']
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
    transform[:3, 3] = frame['origin_mm']
    quality = cfg['render']

    def add(name, material, mesh, spec, finish=False):
        result = mesh.copy()
        result.apply_transform(transform)
        result.vertices /= 1000
        extras = {
            'room_number': spec['room_number'], 'interior_layer': 'selected',
            'bathroom_fixture': spec['id'], 'small_bathroom_fixture': True,
            'provenance': spec.get('provenance', cfg['provenance']),
            'design_status': cfg['status'], 'product_status': 'generic_concept_not_selected_product',
            'material_status': 'concept_palette_not_selected_product',
            'local_bathroom_frame': frame,
        }
        if finish:
            extras.update(bathroom_finish=True, finish_surface=spec['id'], finish_role=spec['role'])
        category = 'sufity' if spec.get('role') == 'ceiling' else 'wnetrze_elementy'
        emit(name, category, material, result,
             'Wizualizacje małej łazienki i pralni; koncepcja dopasowana do R02/R03',
             True, spec.get('note', spec.get('role', '')), spec['id'], extras)

    def box(bounds):
        lower, upper = np.asarray(bounds, float)
        if np.any(upper <= lower):
            raise ValueError(f'Invalid box bounds: {bounds}')
        mesh = trimesh.creation.box(extents=upper-lower)
        mesh.apply_translation((lower+upper)/2)
        return mesh

    def cylinder(spec):
        return trimesh.creation.cylinder(radius=spec['radius_mm'],
            segment=np.asarray([spec['start_mm'], spec['end_mm']], float),
            sections=int(spec.get('segments', quality['pipe_segments'])))

    def pipe(spec):
        points = np.asarray(spec['path_mm'], float)
        meshes = [cylinder({'start_mm': a, 'end_mm': b, 'radius_mm': spec['radius_mm']})
                  for a, b in zip(points, points[1:])]
        for point in points[1:-1]:
            mesh = trimesh.creation.icosphere(subdivisions=quality['pipe_joint_subdivisions'],
                                             radius=spec['radius_mm'])
            mesh.apply_translation(point)
            meshes.append(mesh)
        return meshes

    def pattern(spec):
        bounds = np.asarray(spec['bounds_mm'], float)
        axis = int(spec['repeat_axis'])
        width, pitch = spec['width_mm'], spec['pitch_mm']
        meshes = []
        positions = np.arange(bounds[0, axis], bounds[1, axis]-width+1e-6, pitch)
        for position in positions:
            lower, upper = bounds.copy()
            lower[axis], upper[axis] = position, position+width
            pieces = [(lower, upper)]
            for hole in spec.get('openings_mm', []):
                # Lamella strips are split vertically at declared niche bounds.
                h0, h1 = np.asarray(hole, float)
                if lower[axis] < h1[axis] and upper[axis] > h0[axis]:
                    pieces = [(lo, hi) for a, b in pieces for lo, hi in
                        ((a, np.minimum(b, [np.inf, np.inf, h0[2]])),
                         (np.maximum(a, [-np.inf, -np.inf, h1[2]]), b)) if np.all(hi > lo)]
            meshes.extend(box([lo, hi]) for lo, hi in pieces)
        return meshes

    def surface_meshes(spec):
        lo, hi = np.asarray(spec['bounds_mm'], float)
        axes = spec['uv_axes']
        normal = next(axis for axis in range(3) if axis not in axes)
        domain = rectangle(lo[axes[0]], lo[axes[1]], hi[axes[0]], hi[axes[1]])
        holes = [rectangle(*bounds) for bounds in spec.get('openings_uv_mm', [])]
        if holes:
            domain = domain.difference(unary_union(holes))
        thickness = hi[normal]-lo[normal]
        meshes = []
        tile_u, tile_v = spec['tile_size_mm']
        grout = spec['grout_width_mm']
        for u in np.arange(lo[axes[0]], hi[axes[0]], tile_u):
            for v in np.arange(lo[axes[1]], hi[axes[1]], tile_v):
                region = rectangle(u+grout/2, v+grout/2,
                    min(u+tile_u, hi[axes[0]])-grout/2,
                    min(v+tile_v, hi[axes[1]])-grout/2).intersection(domain)
                polygons = list(region.geoms) if hasattr(region, 'geoms') else [region]
                for polygon in polygons:
                    if polygon.is_empty or polygon.area <= 0:
                        continue
                    mesh = trimesh.creation.extrude_polygon(polygon, thickness, engine='earcut')
                    local = np.asarray(mesh.vertices).copy()
                    vertices = np.empty_like(local)
                    vertices[:, axes[0]], vertices[:, axes[1]] = local[:, 0], local[:, 1]
                    vertices[:, normal] = local[:, 2]+lo[normal]
                    mesh.vertices = vertices
                    if mesh.volume < 0:
                        mesh.invert()
                    meshes.append(mesh)
        return meshes

    for surface in cfg['surfaces']:
        meshes = surface_meshes(surface)
        if meshes:
            add(surface['id'], surface['material'], trimesh.util.concatenate(meshes), surface, True)

    for spec in cfg['elements']:
        meshes = [box(bounds) for bounds in spec.get('boxes_mm', [])]
        meshes.extend(cylinder(item) for item in spec.get('cylinders', []))
        for item in spec.get('pipes', []):
            meshes.extend(pipe(item))
        for item in spec.get('patterns', []):
            meshes.extend(pattern(item))
        for item in spec.get('vessels', []):
            mesh = vessel_mesh(item['profile_mm'], quality['ring_segments'], item['exponent'],
                               annulus=item.get('annulus', False))
            mesh.apply_translation(item['center_mm'])
            meshes.append(mesh)
        for item in spec.get('annuli', []):
            start, end = np.asarray([item['start_mm'], item['end_mm']], float)
            length = np.linalg.norm(end-start)
            outer, inner = item['outer_radius_mm']*2, item['inner_radius_mm']*2
            mesh = vessel_mesh([[outer, outer, 0], [outer, outer, length],
                                [inner, inner, length], [inner, inner, 0]],
                               quality['ring_segments'], 2, annulus=True)
            rotation = trimesh.geometry.align_vectors([0, 0, 1], (end-start)/length)
            mesh.apply_transform(rotation)
            mesh.apply_translation(start)
            meshes.append(mesh)
        if meshes:
            add(spec['id'], spec['material'], trimesh.util.concatenate(meshes), spec,
                bool(spec.get('finish')))
