"""Declarative bathroom fixtures: dimensional concept meshes, not manufacturer CAD.

All dimensions and placements come from modules/06_interior/extracts/bathroom.yaml.
The local frame is mapped to the canonical building frame only at emission time.
"""
from __future__ import annotations

import math
from itertools import permutations, product
from pathlib import Path

import numpy as np
import trimesh
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent


def vessel_mesh(profile_mm, segments=64, exponent=2.8, annulus=False,
                rim_lift_mm=None, rim_lift_exponent=1):
    """Closed ceramic shell with a visible cavity; profile follows outer then inner wall."""
    theta = np.arange(segments) * (2 * math.pi / segments)
    cx = np.sign(np.cos(theta)) * np.abs(np.cos(theta)) ** (2 / exponent)
    cy = np.sign(np.sin(theta)) * np.abs(np.sin(theta)) ** (2 / exponent)
    lifts = rim_lift_mm if rim_lift_mm is not None else np.zeros(len(profile_mm))
    if len(lifts) != len(profile_mm):
        raise ValueError('Every vessel profile ring needs its declared rim lift')
    lift_factor = ((cx+1)/2) ** rim_lift_exponent
    rings = [np.column_stack([cx*w/2, cy*d/2, z+lift*lift_factor])
             for (w, d, z), lift in zip(profile_mm, lifts)]
    vertices = np.vstack(rings).tolist()
    faces = []
    pairs = [(i, i+1) for i in range(len(rings)-1)]
    if annulus:
        pairs.append((len(rings)-1, 0))
    for lower, upper in pairs:
        for k in range(segments):
            nxt = (k+1) % segments
            a, b, c, d = lower*segments+k, lower*segments+nxt, upper*segments+nxt, upper*segments+k
            faces.extend([[a, b, c], [a, c, d]])
    if not annulus:
        for ring_index, reverse in ((0, True), (len(rings)-1, False)):
            center = len(vertices)
            vertices.append([0, 0, profile_mm[ring_index][2] + lifts[ring_index]*(.5**rim_lift_exponent)])
            for k in range(segments):
                a, b = ring_index*segments+k, ring_index*segments+(k+1)%segments
                faces.append([center, b, a] if reverse else [center, a, b])
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _proper_axis_rotations():
    """Yield the 24 rigid axis permutations without reflections."""
    for permutation in permutations(range(3)):
        base = np.zeros((3, 3), dtype=float)
        for target_axis, source_axis in enumerate(permutation):
            base[target_axis, source_axis] = 1.0
        for signs in product((-1.0, 1.0), repeat=3):
            rotation = np.diag(signs) @ base
            if np.linalg.det(rotation) > 0.5:
                yield rotation


def _surface_offset_signature(mesh):
    """Area-weighted surface centroid relative to the bounding-box centre."""
    bounds = np.asarray(mesh.bounds, dtype=float)
    extents = np.maximum(bounds[1] - bounds[0], 1e-9)
    centre = bounds.mean(axis=0)
    triangles = np.asarray(mesh.triangles, dtype=float)
    if not len(triangles):
        return np.zeros(3)
    tri_centres = triangles.mean(axis=1)
    weights = np.asarray(mesh.area_faces, dtype=float)
    if not np.isfinite(weights).all() or weights.sum() <= 0:
        surface_centre = tri_centres.mean(axis=0)
    else:
        surface_centre = np.average(tri_centres, axis=0, weights=weights)
    return (surface_centre - centre) / extents


def manufacturer_obj_mesh(spec, reference_mesh):
    """Load the selected manufacturer OBJ and rigidly fit it to a local proxy.

    The proxy is used only for placement/orientation. The emitted vertices/faces
    remain the manufacturer's mesh: no decimation, remeshing or shape editing.
    """
    model = spec.get('manufacturer_model')
    if not model:
        return None
    if model.get('format', 'obj').lower() != 'obj':
        raise ValueError(f"Unsupported manufacturer model format for {spec.get('id')}: {model.get('format')}")
    path = (ROOT / model['asset_path']).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Manufacturer model path escapes repository: {model['asset_path']}")
    if not path.is_file():
        if model.get('required', True):
            raise FileNotFoundError(f"Required manufacturer OBJ missing: {model['asset_path']}")
        return None

    loaded = trimesh.load(path, force='scene', process=False)
    mesh = loaded.to_geometry()
    if mesh is None or not len(mesh.vertices) or not len(mesh.faces):
        raise ValueError(f"Empty manufacturer OBJ: {model['asset_path']}")
    mesh = mesh.copy()

    target_bounds = np.asarray(reference_mesh.bounds, dtype=float)
    target_extents = np.maximum(target_bounds[1] - target_bounds[0], 1e-9)
    target_centre = target_bounds.mean(axis=0)
    target_signature = _surface_offset_signature(reference_mesh)

    source_unit_scale_mm = float(model.get('source_unit_scale_mm', 1.0))
    if not math.isfinite(source_unit_scale_mm) or source_unit_scale_mm <= 0:
        raise ValueError(f"Invalid manufacturer OBJ unit scale for {spec.get('id')}")

    source_up = None
    source_up_axis = model.get('source_up_axis')
    if source_up_axis is not None:
        axis_index = {'x': 0, 'y': 1, 'z': 2}.get(str(source_up_axis).lower())
        if axis_index is None:
            raise ValueError(f"Invalid manufacturer OBJ up axis for {spec.get('id')}: {source_up_axis}")
        source_up_sign = float(model.get('source_up_sign', 1.0))
        if not math.isfinite(source_up_sign) or source_up_sign not in (-1.0, 1.0):
            raise ValueError(f"Invalid manufacturer OBJ up sign for {spec.get('id')}: {source_up_sign}")
        source_up = np.zeros(3, dtype=float)
        source_up[axis_index] = source_up_sign

    best = None
    source_vertices = np.asarray(mesh.vertices, dtype=float)
    for rotation in _proper_axis_rotations():
        if source_up is not None and float((rotation @ source_up)[2]) < 0.5:
            continue
        rotated = source_vertices @ rotation.T
        bounds = np.vstack([rotated.min(axis=0), rotated.max(axis=0)])
        extents = np.maximum(bounds[1] - bounds[0], 1e-9) * source_unit_scale_mm
        extent_error = float(np.mean(np.abs(np.log(np.maximum(extents, 1e-9) / target_extents))))

        candidate = mesh.copy()
        candidate.vertices = rotated * source_unit_scale_mm
        candidate_signature = _surface_offset_signature(candidate)
        signature_error = float(np.linalg.norm(candidate_signature - target_signature))
        score = extent_error + 0.18 * signature_error
        if best is None or score < best[0]:
            best = (score, rotation)

    if best is None:
        raise ValueError(f"No valid manufacturer OBJ orientation for {spec.get('id')}")
    _, rotation = best
    mesh.vertices = source_vertices @ rotation.T * source_unit_scale_mm
    fitted_bounds = np.asarray(mesh.bounds, dtype=float)
    mesh.apply_translation(target_centre - fitted_bounds.mean(axis=0))
    return mesh


def build_bathroom(configuration, emit, *, finishes=None):
    """Emit separate blocks and selected fixtures through the canonical mesh contract."""
    if not configuration:
        return
    if finishes and not finishes.get('enabled', True):
        finishes = None
    cfg = configuration
    render = cfg['render']
    segments, pipe_segments = int(render['ring_segments']), int(render['pipe_segments'])
    frame = cfg['frame']
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack([frame['x_axis'], frame['y_axis'], frame['z_axis']])
    transform[:3, 3] = frame['origin_mm']
    source = 'Wieloujęciowe wizualizacje łazienki; koncepcja dopasowana do R07'

    def add(name, material, mesh, fixture, *, layer='selected', detail=''):
        result = mesh.copy()
        result.apply_transform(transform)
        result.vertices /= 1000.0
        is_finish = bool(fixture.get('bathroom_finish'))
        material = (finishes or {}).get('part_material_overrides', {}).get(name, material)
        category = 'wnetrze_bloki' if layer == 'blocks' else 'wnetrze_elementy'
        if is_finish and fixture.get('role') == 'ceiling':
            category = 'sufity'
        manufacturer_model = fixture.get('manufacturer_model')
        product = fixture.get('product', {})
        extras = {
                 'room_number': cfg['room_number'], 'interior_layer': layer,
                 'bathroom_fixture': fixture['id'], 'provenance': cfg['provenance'],
                 'design_status': cfg['status'],
                 'product_status': 'selected_manufacturer_obj' if manufacturer_model else 'generic_concept_not_selected_product',
                 'material_status': 'concept_palette_not_selected_product' if finishes else 'neutral_preview_no_tile_selection',
                 'local_bathroom_frame': frame,
             }
        if manufacturer_model:
            extras.update(
                manufacturer_geometry=True,
                manufacturer_model_path=manufacturer_model['asset_path'],
                manufacturer_model_format=manufacturer_model.get('format', 'obj'),
                manufacturer_model_source_id=manufacturer_model.get('source_id'),
                manufacturer=product.get('manufacturer'),
                product_code=product.get('code'),
            )
        if is_finish:
            extras.update(bathroom_finish=True, finish_surface=fixture['id'],
                          finish_role=fixture.get('role'), provenance=finishes['provenance'],
                          design_status=finishes['status'])
            if fixture.get('uv_axes') is not None:
                extras['finish_uv_axes'] = fixture['uv_axes']
                extras['finish_face_side'] = fixture['face_side']
                if fixture.get('grid_origin_uv_mm') is not None:
                    extras['finish_grid_origin_uv_mm'] = fixture['grid_origin_uv_mm']
        emit(name, category, material, result,
             source, True, detail or fixture.get('role', ''), fixture['id'], extras)

    def box_mesh(bounds):
        lo, hi = np.asarray(bounds, dtype=float)
        mesh = trimesh.creation.box(extents=hi-lo)
        mesh.apply_translation((lo+hi)/2)
        return mesh

    def rounded_box(bounds, radius):
        lo, hi = np.asarray(bounds, dtype=float)
        polygon = box(lo[0]+radius, lo[1]+radius, hi[0]-radius, hi[1]-radius).buffer(
            radius, quad_segs=int(render['cabinet_corner_segments']))
        mesh = trimesh.creation.extrude_polygon(polygon, hi[2]-lo[2], engine='earcut')
        mesh.apply_translation([0, 0, lo[2]])
        return mesh

    def cylinder(start, end, radius, count=None):
        a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        return trimesh.creation.cylinder(radius=radius, segment=np.vstack([a, b]), sections=count or pipe_segments)

    def sphere(center, radius, subdivisions=None):
        mesh = trimesh.creation.icosphere(subdivisions=int(render['sphere_subdivisions'] if subdivisions is None else subdivisions), radius=radius)
        mesh.apply_translation(center)
        return mesh

    def combine(meshes):
        valid = [mesh for mesh in meshes if mesh is not None and len(mesh.vertices)]
        if not valid:
            raise ValueError('Cannot combine an empty mesh list')
        return trimesh.util.concatenate(valid)

    def pipe(path, radius):
        points = np.asarray(path, dtype=float)
        return combine([cylinder(a, b, radius) for a, b in zip(points, points[1:])] +
                       [sphere(p, radius, render['pipe_joint_subdivisions']) for p in points[1:-1]])

    def vessel(spec, center, key='profile_mm', annulus=False):
        mesh = vessel_mesh(spec[key], segments, spec.get('exponent', render['vessel_exponent']), annulus,
                           spec.get('rim_lift_mm'), spec.get('rim_lift_exponent', 1))
        mesh.apply_translation(center)
        return mesh

    def accessory_proxy(accessory):
        meshes = [box_mesh(bounds) for bounds in accessory.get('boxes', [])]
        meshes.extend(cylinder(item['start_mm'], item['end_mm'], item['radius_mm'])
                      for item in accessory.get('cylinders', []))
        meshes.extend(pipe(item['path_mm'], item['radius_mm'])
                      for item in accessory.get('pipes', []))
        return combine(meshes)

    def manufacturer_fixture_spec(parent, selected):
        result = dict(parent)
        if selected.get('manufacturer_model'):
            result['manufacturer_model'] = selected['manufacturer_model']
        if selected.get('product'):
            result['product'] = selected['product']
        return result

    def cabinet(spec, label, side='max_x'):
        lo, hi = np.asarray(spec['bbox_mm'], dtype=float)
        body_lo, body_hi = lo.copy(), hi.copy()
        radius, inset = float(spec['flute_radius_mm']), float(spec['body_front_recess_mm'])
        if side == 'max_x':
            body_hi[0] -= inset
            flute_x = hi[0]-radius
        else:
            body_lo[0] += inset
            flute_x = lo[0]+radius
        add(label+'_body', spec['material'], rounded_box([body_lo, body_hi], spec['corner_radius_mm']), spec,
            detail='Wiszący korpus szafki' if side == 'max_x' else 'Płytka zabudowa ściany WC')
        count = max(2, int((hi[1]-lo[1]-2*spec['corner_radius_mm']) / spec['flute_pitch_mm']))
        flutes = []
        ranges = [(lo[2], hi[2])]
        if spec.get('door_split_z_mm'):
            split, reveal = spec['door_split_z_mm'], spec['reveal_height_mm']
            ranges = [(lo[2], split-reveal/2), (split+reveal/2, hi[2])]
        for y in np.linspace(lo[1]+spec['corner_radius_mm'], hi[1]-spec['corner_radius_mm'], count):
            for z0, z1 in ranges:
                flutes.append(cylinder([flute_x, y, z0], [flute_x, y, z1], radius))
        add(label+'_fluted_fronts', spec['material'], combine(flutes), spec, detail='Pionowe ryflowane fronty')

    for block in cfg['blocks']:
        add('BLK_'+block['id'], 'interior_block', box_mesh(block['bbox_mm']), block, layer='blocks')

    fixtures = cfg['fixtures']
    vanity = fixtures['vanity']
    cabinet(vanity, 'SEL_BATH_VANITY')
    add('SEL_BATH_VANITY_countertop', vanity['countertop_material'],
        rounded_box(vanity['countertop_bbox_mm'], vanity['countertop_corner_radius_mm']), vanity,
        detail='Neutralny blat — materiał do późniejszego wyboru')
    add('SEL_BATH_VANITY_lower_shelf', vanity['material'],
        rounded_box(vanity['shelf_bbox_mm'], vanity['shelf_corner_radius_mm']), vanity,
        detail='Niska półka pod wiszącą szafką')

    basins = fixtures['basins']
    for index, center in enumerate(basins['centers_mm'], 1):
        prefix = f'SEL_BATH_BASIN_{index}'
        add(prefix+'_bowl', basins['material'], vessel(basins, center), basins,
            detail='Umywalka nablatowa z modelowanym wnętrzem misy')
        cx, cy, cz = center
        add(prefix+'_drain', fixtures['shower']['material'],
            cylinder([cx, cy, cz+basins['drain_floor_mm']],
                     [cx, cy, cz+basins['drain_floor_mm']+basins['drain_height_mm']], basins['drain_radius_mm']), basins)
        faucet = basins['faucet']
        path = np.asarray(faucet['path_relative_mm']) + np.asarray(center)
        lever = np.asarray(center)+np.asarray(faucet['lever_center_relative_mm'])
        lever_end = lever + [0, faucet['lever_length_mm'], 0]
        if faucet.get('mounting') in ('standing_countertop', 'standing', 'deck'):
            base_pt = path[0]
            rosette = cylinder(base_pt, base_pt + [0, 0, 5], 25.5)
            pillar = cylinder(base_pt, base_pt + [0, 0, 278], 18)
            cap = cylinder(base_pt + [0, 0, 278], base_pt + [0, 0, 305], 17.5)
            pin_lever = cylinder(base_pt + [0, 0, 298], base_pt + [55, 0, 298], 4.5)
            pin_tip = sphere(base_pt + [55, 0, 298], 4.5)
            spout_path = [
                base_pt + [15, 0, 235],
                base_pt + [50, 0, 258],
                base_pt + [100, 0, 268],
                base_pt + [145, 0, 252],
                base_pt + [170, 0, 225],
            ]
            spout = pipe(spout_path, 10.5)
            aerator = cylinder(base_pt + [170, 0, 225], base_pt + [170, 0, 220], 11)
            faucet_parts = [rosette, pillar, cap, pin_lever, pin_tip, spout, aerator]
            prod_info = faucet.get('product', {})
            detail = f"{prod_info.get('type', 'Bateria umywalkowa wysoka')} Omnires Y ({prod_info.get('code', 'Y1212BSB')})"
        else:
            plates = [cylinder(start-[faucet['mounting_plate_depth_mm'],0,0], start,
                               faucet['mounting_plate_radius_mm']) for start in (path[0], lever)]
            faucet_parts = [pipe(path, faucet['radius_mm']),
                            cylinder(lever, lever_end, faucet['lever_radius_mm'])] + plates
            detail = 'Bateria ścienna według jasnego wariantu referencji — przyjęcie koncepcyjne'
        faucet_proxy = combine(faucet_parts)
        faucet_mesh = manufacturer_obj_mesh(faucet, faucet_proxy) or faucet_proxy
        faucet_fixture = manufacturer_fixture_spec(basins, faucet)
        add(prefix+'_faucet', faucet['material'], faucet_mesh, faucet_fixture,
            detail=detail)

    mirrors = fixtures['mirrors']
    x0, x1 = mirrors['x_mm']; y0, y1 = mirrors['y_mm']; z0, z1 = mirrors['z_mm']
    add('SEL_BATH_MIRROR', mirrors['material'], box_mesh([[x0, y0, z0], [x1, y1, z1]]), mirrors,
        detail='Jedno szerokie lustro — powierzchnia poglądowa, bez symulacji odbicia')
    width, depth = mirrors['edge_width_mm'], mirrors['edge_depth_mm']
    strips = [box_mesh([[x1, y0, z0], [x1+depth, y0+width, z1]]),
              box_mesh([[x1, y1-width, z0], [x1+depth, y1, z1]])]
    add('SEL_BATH_MIRROR_light_edges', mirrors['edge_material'], combine(strips), mirrors,
        detail='Poglądowe podświetlenie pionowych krawędzi jednego lustra')

    pendants = fixtures['pendants']
    for index, (x, y) in enumerate(pendants['centers_xy_mm'], 1):
        z0, z1 = pendants['bottom_z_mm'], pendants['canopy_z_mm']
        rods = [cylinder([x,y,z0], [x,y,z1], pendants['stem_radius_mm']),
                cylinder([x,y,z1], [x,y,z1+pendants['canopy_height_mm']], pendants['canopy_radius_mm'])]
        add(f'SEL_BATH_PENDANT_{index}_metal', pendants['material'], combine(rods), pendants)
        centers = [np.array([x, y, z0])+offset for offset in np.asarray(pendants['globe_offsets_mm'])]
        add(f'SEL_BATH_PENDANT_{index}_glass', pendants['globe_material'],
            combine([sphere(c, pendants['globe_radius_mm']) for c in centers]), pendants)
        add(f'SEL_BATH_PENDANT_{index}_light', mirrors['edge_material'],
            combine([sphere(c, pendants['globe_core_radius_mm']) for c in centers]), pendants)

    tub = fixtures['bathtub']
    tub_proxy = vessel(tub, tub['center_mm'])
    tub_mesh = manufacturer_obj_mesh(tub, tub_proxy) or tub_proxy
    tub_rotation_deg = float(tub.get('rotation_z_deg', 0.0))
    if tub_rotation_deg:
        tub_mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(tub_rotation_deg), [0, 0, 1],
            point=np.asarray(tub['center_mm'], dtype=float)))
    add('SEL_BATH_TUB_shell', tub['material'], tub_mesh, tub,
        detail=('Cersanit Inverto S301-372 — oficjalna geometria OBJ producenta, '
                f'obrócona o {tub_rotation_deg:g}°')
               if tub.get('manufacturer_model') else
               'Wanna wolnostojąca z obrzeżem, dnem i wklęsłą misą')
    cx, cy, cz = tub['center_mm']
    if not tub.get('manufacturer_model'):
        add('SEL_BATH_TUB_drain', fixtures['shower']['material'], cylinder(
            [cx,cy,cz+tub['drain_floor_mm']], [cx,cy,cz+tub['drain_floor_mm']+tub['drain_height_mm']], tub['drain_radius_mm']), tub)
    tap = tub['faucet']
    foot = np.asarray(tap['path_mm'][0], dtype=float)
    rosette = cylinder(foot, foot + [0, 0, tap.get('foot_height_mm', 12)], tap.get('foot_radius_mm', 75))
    pillar_low = cylinder(foot + [0, 0, 12], foot + [0, 0, 650], 21)
    mixer_center = foot + [0, 0, 650]
    mixer_bar = cylinder(mixer_center - [0, 60, 0], mixer_center + [0, 60, 0], 21)
    diverter = cylinder(mixer_center, mixer_center + [0, 0, 30], 10)
    lever = cylinder(mixer_center + [0, 60, 0], mixer_center + [25, 60, 20], 4.5)
    lever_tip = sphere(mixer_center + [25, 60, 20], 4.5)
    bracket = cylinder(mixer_center - [0, 60, 0], mixer_center - [0, 95, 0], 12)
    wand_base = mixer_center - [0, 95, 0]
    wand = cylinder(wand_base, wand_base + [0, 0, 210], 12)
    wand_cap = sphere(wand_base + [0, 0, 210], 12)
    hose_path = [
        wand_base,
        wand_base - [15, 10, 80],
        wand_base - [15, 0, 220],
        wand_base + [0, 15, 270],
        mixer_center - [0, 30, 200],
        mixer_center - [0, 20, 20],
    ]
    hose = pipe(hose_path, 6.5)
    spout = pipe(tap['path_mm'], tap['radius_mm'])
    aerator = cylinder(np.asarray(tap['path_mm'][-1]), np.asarray(tap['path_mm'][-1]) - [0, 0, 12], tap['radius_mm'] + 1)
    tub_faucet_mesh = combine([
        rosette, pillar_low, mixer_bar, diverter, lever, lever_tip,
        bracket, wand, wand_cap, hose, spout, aerator
    ])
    tap_prod = tap.get('product', {})
    tap_detail = f"{tap_prod.get('type', 'Bateria wannowa wolnostojąca wysoka')} Omnires Y ({tap_prod.get('code', 'Y1233BSB')})"
    tub_faucet_proxy = tub_faucet_mesh
    tub_faucet_mesh = manufacturer_obj_mesh(tap, tub_faucet_proxy) or tub_faucet_proxy
    tap_rotation_deg = float(tap.get('rotation_z_deg', 0.0))
    if tap_rotation_deg:
        tub_faucet_mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(tap_rotation_deg), [0, 0, 1], point=foot))
    tap_fixture = manufacturer_fixture_spec(tub, tap)
    add('SEL_BATH_TUB_faucet', tap['material'], tub_faucet_mesh, tap_fixture,
        detail=tap_detail)

    screen = fixtures['shower_screen']; z0, z1 = screen['z_mm']
    half, rail, frame_depth = screen['glass_thickness_mm']/2, screen['frame_width_mm'], screen['frame_depth_mm']/2
    frame_bounds = set()
    for panel in screen['panels']:
        x0, x1 = panel['x_mm']
        y = screen['y_mm'] + panel['y_offset_mm']
        add('SEL_BATH_SCREEN_'+panel['id'], screen['glazing_material'], box_mesh(
            [[x0+rail/2,y-half,z0+rail], [x1-rail/2,y+half,z1-rail]]), screen,
            detail='Przezroczysty panel szklany — koncepcja przegrody')
        top_post_z = screen['header_bbox_mm'][0][2] if 'header_bbox_mm' in screen else z1
        for x in (x0, x1):
            frame_bounds.add((x-rail/2,y-frame_depth,z0,x+rail/2,y+frame_depth,top_post_z))
        top_rail_z = (screen['header_bbox_mm'][0][2] - rail) if 'header_bbox_mm' in screen else (z1 - rail)
        for z in (z0, top_rail_z):
            frame_bounds.add((x0,y-frame_depth,z,x1,y+frame_depth,z+rail))
    add('SEL_BATH_SCREEN_frame', screen['frame_material'], combine([box_mesh([b[:3],b[3:]]) for b in sorted(frame_bounds)]), screen)
    add('SEL_BATH_SCREEN_sliding_header', screen['frame_material'], box_mesh(screen['header_bbox_mm']), screen,
        detail='Górna prowadnica dwóch środkowych skrzydeł przesuwnych')
    rollers = screen['rollers']
    roller_z = screen['header_bbox_mm'][0][2] - rollers['radius_mm'] if 'header_bbox_mm' in screen else rollers['center_z_mm']
    add('SEL_BATH_SCREEN_rollers', screen['frame_material'], combine([
        cylinder([x,rollers['center_y_mm']-rollers['depth_mm']/2,roller_z],
                 [x,rollers['center_y_mm']+rollers['depth_mm']/2,roller_z], rollers['radius_mm'])
        for x in rollers['x_mm']]), screen)
    for index, handle in enumerate(screen['handles'], 1):
        hx,hz=handle['x_mm'],handle['center_z_mm']
        y=screen['y_mm']+handle['y_offset_mm']; hy=y-handle['projection_mm']
        grip = [cylinder([hx,hy,hz-handle['height_mm']/2], [hx,hy,hz+handle['height_mm']/2], handle['radius_mm'])]
        for z in (hz-handle['height_mm']/2, hz+handle['height_mm']/2):
            grip.append(cylinder([hx,hy,z], [hx,y,z], handle['radius_mm']))
        add(f'SEL_BATH_SCREEN_handle_{index}', screen['frame_material'], combine(grip), screen)

    shower = fixtures['shower']; x,y,z = shower['head_center_mm']; thick=shower['head_thickness_mm']
    wall_x = float(shower.get('controls_center_mm', [2592.4, y, 1120])[0] + shower.get('controls_depth_mm', 20))
    arm_path = [
        [wall_x - 30, y, z - 20],
        [wall_x - 30, y, z + 40],
        [wall_x - 60, y, z + 60],
        [x + 40, y, z + 60],
        [x, y, z + 40],
        [x, y, z + thick/2],
    ]
    shower_head_mesh = combine([
        pipe(arm_path, shower.get('stem_radius_mm', 11)),
        cylinder([x, y, z - thick/2], [x, y, z + thick/2], shower['head_radius_mm'], segments),
        cylinder([wall_x - 30, y, z - 20], [wall_x, y, z - 20], 30),
    ])
    shower_prod = shower.get('product', {})
    shower_detail = f"{shower_prod.get('type', 'Termostatyczny system prysznicowy natynkowy')} Omnires Y ({shower_prod.get('code', 'Y1244SUBSB')})"
    pitch=shower['nozzle_grid_pitch_mm']; nozzles=[]
    for dx in np.arange(-shower['head_radius_mm']+pitch, shower['head_radius_mm'], pitch):
        for dy in np.arange(-shower['head_radius_mm']+pitch, shower['head_radius_mm'], pitch):
            if math.hypot(dx,dy)+shower['nozzle_radius_mm'] < shower['head_radius_mm']:
                nozzles.append(cylinder([x+dx,y+dy,z-thick/2-shower['nozzle_depth_mm']], [x+dx,y+dy,z-thick/2], shower['nozzle_radius_mm']))
    shower_nozzles_mesh = combine(nozzles)
    cx, cy, cz = shower['controls_center_mm']
    bar_x = cx - 52.4
    rosette_l = cylinder([bar_x, cy - 75, cz], [wall_x, cy - 75, cz], 30)
    rosette_r = cylinder([bar_x, cy + 75, cz], [wall_x, cy + 75, cz], 30)
    bar = cylinder([bar_x, cy - 140, cz], [bar_x, cy + 140, cz], 21)
    knob_l = cylinder([bar_x, cy - 140, cz], [bar_x, cy - 170, cz], 21.5)
    knob_r = cylinder([bar_x, cy + 140, cz], [bar_x, cy + 170, cz], 21.5)
    rail = cylinder([bar_x, cy, cz], [bar_x, cy, z - 40], 11)
    top_bracket = cylinder([bar_x, cy, z - 120], [wall_x, cy, z - 120], 15)
    shower_mixer_mesh = combine([rosette_l, rosette_r, bar, knob_l, knob_r, rail, top_bracket])
    shower_handset = next((item for item in fixtures.get('accessories', [])
                           if item.get('id') == 'BATH_SHOWER_HANDSET'), None)
    shower_reference_parts = [shower_head_mesh, shower_nozzles_mesh, shower_mixer_mesh]
    if shower_handset:
        shower_reference_parts.append(accessory_proxy(shower_handset))
    shower_proxy = combine(shower_reference_parts)
    shower_exact = manufacturer_obj_mesh(shower, shower_proxy)
    if shower_exact is not None:
        add('SEL_BATH_SHOWER_system', shower['material'], shower_exact, shower,
            detail=shower_detail + ' — oficjalna geometria OBJ producenta')
    else:
        add('SEL_BATH_SHOWER_head', shower['material'], shower_head_mesh, shower,
            detail=shower_detail)
        add('SEL_BATH_SHOWER_nozzles', shower['nozzle_material'], shower_nozzles_mesh, shower)
        add('SEL_BATH_SHOWER_mixer', shower['material'], shower_mixer_mesh, shower,
            detail="Bateria termostatyczna natynkowa Omnires Y1244SUBSB (mosiądz szczotkowany BSB)")

    wc = fixtures['toilet']
    add('SEL_BATH_WC_bowl', wc['material'], vessel(wc, wc['center_mm'], 'body_profile_mm'), wc,
        detail='Obła miska WC wiszącego')
    add('SEL_BATH_WC_seat', wc['material'], vessel(wc, wc['center_mm'], 'seat_profile_mm', annulus=True), wc,
        detail='Obła deska WC z otworem')
    carrier = wc.get('carrier_frame', {})
    service_detail = f"Obudowa stelaża WC {carrier.get('manufacturer', 'Acaplast')} {carrier.get('code', 'AM101/1120')}" if carrier else 'Umowna obudowa stelaża, instalacja niezweryfikowana'
    add('SEL_BATH_WC_service_box', wc['service_box_material'], box_mesh(wc['service_box_bbox_mm']), wc,
        detail=service_detail)
    add('SEL_BATH_WC_flush_plate', wc['flush_material'], box_mesh(wc['flush_plate_bbox_mm']), wc)

    cabinet(fixtures['wc_storage_upper'], 'SEL_BATH_WC_STORAGE_UPPER', 'min_x')
    cabinet(fixtures['wc_storage_side'], 'SEL_BATH_WC_STORAGE_SIDE', 'min_x')

    for accessory in fixtures['accessories']:
        if accessory.get('id') == 'BATH_SHOWER_HANDSET' and shower.get('manufacturer_model'):
            continue
        proxy = accessory_proxy(accessory)
        mesh = manufacturer_obj_mesh(accessory, proxy) or proxy
        add('SEL_'+accessory['id'], accessory['material'], mesh, accessory,
            detail=(accessory['detail'] + ' — oficjalna geometria OBJ producenta'
                    if accessory.get('manufacturer_model') else accessory['detail']))

    if finishes:
        _build_finishes(finishes, add, box_mesh, cylinder, combine)


def _build_finishes(configuration, add, box_mesh, cylinder, combine):
    """Native closed tile panels, paint and lighting in the bathroom frame.

    Surface rectangles and cutouts are declarative. Tiling is clipped against the
    source openings before extrusion, so no paint or tile closes the windows
    or entry. No raster image is used to impersonate scene geometry.
    """
    cfg = configuration
    tiling = dict(cfg['tile_layout'])
    preset_key = tiling.get('active_format')
    if preset_key and 'tile_format_presets' in cfg and preset_key in cfg['tile_format_presets']:
        tiling.update(cfg['tile_format_presets'][preset_key])

    def polygons(geometry):
        if geometry.is_empty:
            return []
        if geometry.geom_type == 'Polygon':
            return [geometry]
        return [p for p in geometry.geoms if p.geom_type == 'Polygon' and p.area > 0]

    def extrude_uv(geometry, lower, upper, uv_axes):
        normal_axis = next(axis for axis in range(3) if axis not in uv_axes)
        transform = np.eye(4)
        transform[:3, :3] = np.eye(3)[:, [*uv_axes, normal_axis]]
        transform[normal_axis, 3] = lower
        meshes = []
        for polygon in polygons(geometry):
            mesh = trimesh.creation.extrude_polygon(polygon, upper-lower, engine='earcut')
            mesh.apply_transform(transform)
            meshes.append(mesh)
        return meshes

    def finish_spec(spec):
        return {**spec, 'bathroom_finish': True}

    for surface in cfg['surfaces']:
        spec = finish_spec(surface)
        lo, hi = np.asarray(surface['bbox_mm'], dtype=float)
        u, v = surface['uv_axes']
        normal_axis = next(axis for axis in range(3) if axis not in (u, v))
        area = box(lo[u], lo[v], hi[u], hi[v])
        for opening in surface.get('openings_uv_mm', []):
            opening_lo, opening_hi = opening['rect_uv_mm']
            area = area.difference(box(*opening_lo, *opening_hi))
        prefix = 'FIN_BATH_'+surface['id']
        if surface['finish'] == 'paint':
            add(prefix, surface['material'], combine(extrude_uv(area, lo[normal_axis], hi[normal_axis], [u, v])), spec,
                detail=surface.get('note', 'Wykończenie malowane według koncepcji jasnego wariantu'))
            continue

        side_max = surface['face_side'] == 'max'
        tile_depth = min(tiling['facing_depth_mm'], hi[normal_axis]-lo[normal_axis])
        recess = tiling['grout_recess_mm']
        back_lo, back_hi = lo[normal_axis], hi[normal_axis]
        if side_max:
            back_hi -= recess
            tile_lo, tile_hi = hi[normal_axis]-tile_depth, hi[normal_axis]
        else:
            back_lo += recess
            tile_lo, tile_hi = lo[normal_axis], lo[normal_axis]+tile_depth
        add(prefix+'_grout', tiling['grout_material'], combine(extrude_uv(area, back_lo, back_hi, [u, v])), spec,
            detail='Cofnięta spoina; kolor i szerokość robocze')
        widths = np.asarray(tiling['size_uv_mm'], dtype=float)
        origin = np.asarray(surface['grid_origin_uv_mm'], dtype=float)
        first = np.floor((lo[[u, v]]-origin)/widths).astype(int)
        last = np.ceil((hi[[u, v]]-origin)/widths).astype(int)
        gap = tiling['grout_width_mm']/2
        pieces = []
        for i in range(first[0], last[0]):
            for j in range(first[1], last[1]):
                start = origin+np.array([i, j])*widths
                tile = box(*(start+gap), *(start+widths-gap))
                pieces.extend(extrude_uv(area.intersection(tile), tile_lo, tile_hi, [u, v]))
        add(prefix+'_tiles', tiling['material'], combine(pieces), spec,
            detail=tiling['note'])

    for assembly in (cfg['trims'], cfg['lighting']['cove']):
        add('FIN_BATH_'+assembly['id'], assembly['material'],
            combine([box_mesh(bounds) for bounds in assembly['boxes_mm']]), finish_spec(assembly))

    lights = cfg['lighting']['downlights']
    parts, trims = [], []
    for x, y in lights['centers_xy_mm']:
        z0, z1 = lights['z_mm']
        parts.append(cylinder([x, y, z0], [x, y, z1], lights['radius_mm'], lights['segments']))
        z0, z1 = lights['trim_z_mm']
        trims.append(cylinder([x, y, z0], [x, y, z1], lights['trim_radius_mm'], lights['segments']))
    add('FIN_BATH_'+lights['id'], lights['material'], combine(parts), finish_spec(lights),
        detail='Poglądowe punkty świetlne, bez doboru konkretnej oprawy')
    add('FIN_BATH_'+lights['id']+'_trim', lights['trim_material'], combine(trims), finish_spec(lights))

    blinds = cfg.get('blinds')
    if blinds:
        for window in blinds['windows']:
            width_axis = window['width_axis']
            other_axis = 1-width_axis
            extents = np.zeros(3)
            extents[width_axis] = window['width_mm']
            extents[other_axis] = blinds['slat_depth_mm']
            extents[2] = blinds['slat_thickness_mm']
            rotation_axis = np.eye(3)[width_axis]
            rotation = trimesh.transformations.rotation_matrix(
                math.radians(blinds['slat_tilt_degrees']), rotation_axis)
            slats = []
            z0, z1 = blinds['slat_z_mm']
            for z in np.arange(z0, z1+blinds['slat_pitch_mm']/2, blinds['slat_pitch_mm']):
                mesh = trimesh.creation.box(extents=extents)
                mesh.apply_transform(rotation)
                center = list(window['slat_center_mm'])
                center[2] = z
                mesh.apply_translation(center)
                slats.append(mesh)
            add('FIN_BATH_'+window['id']+'_slats', blinds['material'], combine(slats), finish_spec(window),
                detail='Częściowo otwarte żaluzje; mechanizm i kolizje otwierania okien do uzgodnienia')
            add('FIN_BATH_'+window['id']+'_headrail', blinds['material'], box_mesh(window['headrail_bbox_mm']),
                finish_spec(window))
