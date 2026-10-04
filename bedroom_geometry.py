"""Reference-led bedroom furniture and finishes, entirely parameterized in YAML.

The architectural shell is never modified here. Textile meshes are closed soft
volumes or thin draped sheets, so both the portal and offline renderer share the
same bedding, folds and curtains rather than renderer-only decorations.
"""
from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import box as rectangle
from shapely.ops import unary_union

from bathroom_geometry import vessel_mesh


def _rotate(mesh, spec):
    if spec.get('rotation_degrees'):
        matrix = trimesh.transformations.euler_matrix(*np.radians(spec['rotation_degrees']))
        mesh.apply_transform(matrix)
    if spec.get('center_mm'):
        mesh.apply_translation(spec['center_mm'])
    return mesh


def soft_volume(spec, quality):
    """Closed superellipsoid with explicit upholstery fullness and small ripples."""
    rings, segments = quality['soft_rings'], quality['soft_segments']
    a, b, c = np.asarray(spec['size_mm'], float)/2
    lat_exp, lon_exp = spec['shape_exponents']
    angles = np.arange(segments)*2*np.pi/segments
    power = lambda v, p: np.sign(v)*np.abs(v)**p
    vertices = [[0, 0, -c]]
    for phi in np.linspace(-np.pi/2, np.pi/2, rings+2)[1:-1]:
        latitude = power(np.cos(phi), lat_exp)
        x = a*latitude*power(np.cos(angles), lon_exp)
        y = b*latitude*power(np.sin(angles), lon_exp)
        z = np.full(segments, c*power(np.sin(phi), lat_exp))
        for wave in spec.get('waves', []):
            direction = np.radians(wave['angle_degrees'])
            phase = 2*np.pi*(x*np.cos(direction)+y*np.sin(direction))/wave['wavelength_mm']+wave['phase_radians']
            z += wave['amplitude_mm']*np.sin(phase)*np.cos(phi)**2
        vertices.extend(np.column_stack([x, y, z]).tolist())
    top = len(vertices)
    vertices.append([0, 0, c])
    faces = []
    for j in range(segments):
        nxt = (j+1)%segments
        faces.append([0, 1+nxt, 1+j])
        for row in range(rings-1):
            p, q = 1+row*segments+j, 1+row*segments+nxt
            faces.extend([[p, q, q+segments], [p, q+segments, p+segments]])
        faces.append([top, 1+(rings-1)*segments+j, 1+(rings-1)*segments+nxt])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return _rotate(mesh, spec)


def _closed_grid(vertices, rows, columns, thickness, normal):
    """Add the back face and perimeter of a rectangular sheet without open edges."""
    front = np.asarray(vertices, float)
    count = len(front)
    back = front-np.asarray(normal)*thickness
    faces = []
    for row in range(rows-1):
        for col in range(columns-1):
            a = row*columns+col
            b, c, d = a+1, a+1+columns, a+columns
            faces.extend([[a, b, c], [a, c, d], [a+count, c+count, b+count], [a+count, d+count, c+count]])
    perimeter = (list(range(columns)) + [row*columns+columns-1 for row in range(1, rows)] +
                 list(range((rows-1)*columns+columns-2, (rows-1)*columns-1, -1)) +
                 [row*columns for row in range(rows-2, 0, -1)])
    for a, b in zip(perimeter, perimeter[1:]+perimeter[:1]):
        faces.extend([[a, a+count, b+count], [a, b+count, b]])
    mesh = trimesh.Trimesh(vertices=np.vstack([front, back]), faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def draped_textile(spec, quality):
    """Two declared cross sections provide the bed-edge drop; waves supply folds."""
    nx, ny = spec.get('grid_segments', quality['cloth_segments'])
    xprofile = np.asarray(spec['x_profile_mm'], float)
    yprofile = np.asarray(spec['y_profile_mm'], float)
    xs = np.unique(np.r_[np.linspace(xprofile[0, 0], xprofile[-1, 0], nx+1), xprofile[:, 0]])
    ys = np.unique(np.r_[np.linspace(yprofile[0, 0], yprofile[-1, 0], ny+1), yprofile[:, 0]])
    xx, yy = np.meshgrid(xs, ys)
    zz = np.minimum(np.interp(xx, *xprofile.T), np.interp(yy, *yprofile.T))
    for wave in spec.get('waves', []):
        angle = np.radians(wave['angle_degrees'])
        zz += wave['amplitude_mm']*np.sin(2*np.pi*(xx*np.cos(angle)+yy*np.sin(angle))/wave['wavelength_mm']+wave['phase_radians'])
    mesh = _closed_grid(np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()]),
                        len(ys), len(xs), spec['thickness_mm'], [0, 0, 1])
    return _rotate(mesh, spec)


def curtain(spec, quality):
    """Gathered curtain is a continuous corrugated sheet, not individual boards."""
    lo, hi = np.asarray(spec['bounds_mm'], float)
    along, normal = spec['width_axis'], spec['depth_axis']
    nu, nz = quality['curtain_segments']
    widths = np.linspace(lo[along], hi[along], nu+1)
    heights = np.linspace(lo[2], hi[2], nz+1)
    vertices = []
    for z in heights:
        h = (z-lo[2])/(hi[2]-lo[2])
        for width in widths:
            phase = 2*np.pi*(width-lo[along])/spec['fold_pitch_mm']
            depth = (lo[normal]+hi[normal])/2+spec['fold_depth_mm']/2*np.sin(phase+spec['sway_radians']*(1-h))
            p = np.zeros(3)
            p[along], p[normal], p[2] = width, depth, z
            vertices.append(p)
    direction = np.eye(3)[normal]
    return _closed_grid(vertices, len(heights), len(widths), spec['thickness_mm'], direction)


def build_bedroom(configuration, emit):
    if not configuration or not configuration.get('enabled', True):
        return
    cfg, quality = configuration, configuration['render']
    frame = cfg['frame']
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
    transform[:3, 3] = frame['origin_mm']

    def add(spec, meshes, finish=False):
        if not meshes:
            return
        mesh = trimesh.util.concatenate(meshes)
        texture = {}
        if spec.get('texture_url'):
            u, v = spec['uv_axes']
            n = next(i for i in range(3) if i not in (u, v))
            lo, hi = np.asarray(spec['bounds_mm'], float)
            uv = (mesh.vertices[:, [u, v]]-lo[[u, v]])/(hi[[u, v]]-lo[[u, v]])
            side = lo[n] if spec['face_side'].startswith('min') else hi[n]
            front = np.all(np.isclose(mesh.triangles[:, :, n], side), axis=1)
            texture = dict(texture_url=spec['texture_url'], texture_uv=uv.tolist(),
                           texture_faces=np.flatnonzero(front).tolist())
        mesh.apply_transform(transform)
        mesh.vertices /= 1000
        extra = dict(room_number=cfg['room_number'], interior_layer='selected',
                     interior_fixture=spec['id'], bedroom_fixture=True,
                     provenance=spec.get('provenance', cfg['provenance']),
                     design_status=cfg['status'], product_status='generic_concept_not_selected_product',
                     material_status='concept_palette_not_selected_product', local_interior_frame=frame)
        extra.update(texture)
        if finish:
            extra.update(interior_finish=True, finish_surface=spec['id'], finish_role=spec['role'])
            if 'uv_axes' in spec:
                extra.update(finish_uv_axes=spec['uv_axes'], finish_face_side=spec.get('face_side', 'max'))
        emit(spec['id'], 'sufity' if spec.get('role') == 'ceiling' else 'wnetrze_elementy',
             spec['material'], mesh, 'Zdjęcia referencyjne sypialni; koncepcja dopasowana do R08',
             True, spec.get('note', spec.get('role', '')), spec['id'], extra)

    def box(bounds):
        lo, hi = np.asarray(bounds, float)
        if np.any(hi <= lo):
            raise ValueError(f'Invalid bedroom bounds: {bounds}')
        mesh = trimesh.creation.box(extents=hi-lo)
        mesh.apply_translation((hi+lo)/2)
        return mesh

    def cylinder(spec):
        return trimesh.creation.cylinder(radius=spec['radius_mm'],
            segment=np.asarray([spec['start_mm'], spec['end_mm']], float),
            sections=quality['pipe_segments'])

    def surface(spec):
        lo, hi = np.asarray(spec['bounds_mm'], float)
        u, v = spec['uv_axes']
        n = next(i for i in range(3) if i not in (u, v))
        region = rectangle(lo[u], lo[v], hi[u], hi[v])
        if spec.get('openings_uv_mm'):
            region = region.difference(unary_union([rectangle(*hole) for hole in spec['openings_uv_mm']]))
        pieces = list(region.geoms) if hasattr(region, 'geoms') else [region]
        meshes = []
        for piece in pieces:
            if piece.is_empty or piece.area <= 0:
                continue
            mesh = trimesh.creation.extrude_polygon(piece, hi[n]-lo[n], engine='earcut')
            old = mesh.vertices.copy()
            mesh.vertices[:, u], mesh.vertices[:, v], mesh.vertices[:, n] = old[:, 0], old[:, 1], old[:, 2]+lo[n]
            if mesh.volume < 0:
                mesh.invert()
            meshes.append(mesh)
        return meshes

    for spec in cfg['surfaces']:
        add(spec, surface(spec), True)
    for spec in cfg['elements']:
        meshes = [box(bounds) for bounds in spec.get('boxes_mm', [])]
        meshes.extend(cylinder(item) for item in spec.get('cylinders', []))
        meshes.extend(soft_volume(item, quality) for item in spec.get('soft_volumes', []))
        meshes.extend(draped_textile(item, quality) for item in spec.get('textiles', []))
        meshes.extend(curtain(item, quality) for item in spec.get('curtains', []))
        for pattern in spec.get('patterns', []):
            lo, hi = np.asarray(pattern['bounds_mm'], float)
            axis = pattern['repeat_axis']
            for position in np.arange(lo[axis], hi[axis]-pattern['width_mm']+1e-6, pattern['pitch_mm']):
                a, b = lo.copy(), hi.copy()
                a[axis], b[axis] = position, position+pattern['width_mm']
                meshes.append(box([a, b]))
        for pattern in spec.get('soft_patterns', []):
            for index in range(pattern['count']):
                item = dict(pattern['volume'])
                item['center_mm'] = (np.asarray(item['center_mm'])+index*np.asarray(pattern['step_mm'])).tolist()
                meshes.append(soft_volume(item, quality))
        for item in spec.get('annuli', []):
            start, end = np.asarray([item['start_mm'], item['end_mm']], float)
            length = np.linalg.norm(end-start)
            outer, inner = item['outer_radius_mm']*2, item['inner_radius_mm']*2
            mesh = vessel_mesh([[outer, outer, 0], [outer, outer, length],
                                [inner, inner, length], [inner, inner, 0]], quality['ring_segments'], 2, annulus=True)
            mesh.apply_transform(trimesh.geometry.align_vectors([0, 0, 1], (end-start)/length))
            mesh.apply_translation(start)
            meshes.append(mesh)
        for item in spec.get('polyhedra', []):
            meshes.append(trimesh.convex.convex_hull(np.asarray(item['vertices_mm'], float)))
        add(spec, meshes, bool(spec.get('finish')))
