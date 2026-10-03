"""Declarative bathroom fixtures: dimensional concept meshes, not manufacturer CAD.

All dimensions and placements come from modules/06_interior/extracts/bathroom.yaml.
The local frame is mapped to the canonical building frame only at emission time.
"""
from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import box


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
        extras = {
                 'room_number': cfg['room_number'], 'interior_layer': layer,
                 'bathroom_fixture': fixture['id'], 'provenance': cfg['provenance'],
                 'design_status': cfg['status'], 'product_status': 'generic_concept_not_selected_product',
                 'material_status': 'concept_palette_not_selected_product' if finishes else 'neutral_preview_no_tile_selection',
                 'local_bathroom_frame': frame,
             }
        if is_finish:
            extras.update(bathroom_finish=True, finish_surface=fixture['id'],
                          finish_role=fixture.get('role'), provenance=finishes['provenance'],
                          design_status=finishes['status'])
            if fixture.get('uv_axes') is not None:
                extras['finish_uv_axes'] = fixture['uv_axes']
                extras['finish_face_side'] = fixture['face_side']
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
        return trimesh.util.concatenate(meshes)

    def pipe(path, radius):
        points = np.asarray(path, dtype=float)
        return combine([cylinder(a, b, radius) for a, b in zip(points, points[1:])] +
                       [sphere(p, radius, render['pipe_joint_subdivisions']) for p in points[1:-1]])

    def vessel(spec, center, key='profile_mm', annulus=False):
        mesh = vessel_mesh(spec[key], segments, spec.get('exponent', render['vessel_exponent']), annulus,
                           spec.get('rim_lift_mm'), spec.get('rim_lift_exponent', 1))
        mesh.apply_translation(center)
        return mesh

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
        plates = [cylinder(start-[faucet['mounting_plate_depth_mm'],0,0], start,
                           faucet['mounting_plate_radius_mm']) for start in (path[0], lever)]
        add(prefix+'_faucet', faucet['material'], combine([pipe(path, faucet['radius_mm']),
            cylinder(lever, lever_end, faucet['lever_radius_mm'])]+plates), basins,
            detail='Bateria ścienna według jasnego wariantu referencji — przyjęcie koncepcyjne')

    mirrors = fixtures['mirrors']
    for index, y in enumerate(mirrors['centers_y_mm'], 1):
        x0, x1 = mirrors['x_mm']; z0, z1 = mirrors['z_mm']; half = mirrors['width_mm']/2
        add(f'SEL_BATH_MIRROR_{index}', mirrors['material'], box_mesh([[x0, y-half, z0], [x1, y+half, z1]]), mirrors,
            detail='Lustro — powierzchnia poglądowa, bez symulacji odbicia')
        width, depth = mirrors['edge_width_mm'], mirrors['edge_depth_mm']
        strips = [box_mesh([[x1, y-half, z0], [x1+depth, y-half+width, z1]]),
                  box_mesh([[x1, y+half-width, z0], [x1+depth, y+half, z1]])]
        add(f'SEL_BATH_MIRROR_{index}_light_edges', mirrors['edge_material'], combine(strips), mirrors,
            detail='Poglądowe podświetlenie pionowych krawędzi')

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
    add('SEL_BATH_TUB_shell', tub['material'], vessel(tub, tub['center_mm']), tub,
        detail='Wanna wolnostojąca z obrzeżem, dnem i wklęsłą misą')
    cx, cy, cz = tub['center_mm']
    add('SEL_BATH_TUB_drain', fixtures['shower']['material'], cylinder(
        [cx,cy,cz+tub['drain_floor_mm']], [cx,cy,cz+tub['drain_floor_mm']+tub['drain_height_mm']], tub['drain_radius_mm']), tub)
    tap = tub['faucet']; foot = tap['path_mm'][0]
    add('SEL_BATH_TUB_faucet', tap['material'], combine([pipe(tap['path_mm'], tap['radius_mm']),
        cylinder(foot, np.asarray(foot)+[0,0,tap['foot_height_mm']], tap['foot_radius_mm'])]), tub,
        detail='Bateria wolnostojąca; przyłącza wymagają uzgodnienia')

    screen = fixtures['shower_screen']; z0, z1 = screen['z_mm']
    half, rail, frame_depth = screen['glass_thickness_mm']/2, screen['frame_width_mm'], screen['frame_depth_mm']/2
    frame_bounds = set()
    for panel in screen['panels']:
        x0, x1 = panel['x_mm']
        y = screen['y_mm'] + panel['y_offset_mm']
        add('SEL_BATH_SCREEN_'+panel['id'], screen['glazing_material'], box_mesh(
            [[x0+rail/2,y-half,z0+rail], [x1-rail/2,y+half,z1-rail]]), screen,
            detail='Przezroczysty panel szklany — koncepcja przegrody')
        for x in (x0, x1):
            frame_bounds.add((x-rail/2,y-frame_depth,z0,x+rail/2,y+frame_depth,z1))
        for z in (z0, z1-rail):
            frame_bounds.add((x0,y-frame_depth,z,x1,y+frame_depth,z+rail))
    add('SEL_BATH_SCREEN_frame', screen['frame_material'], combine([box_mesh([b[:3],b[3:]]) for b in sorted(frame_bounds)]), screen)
    add('SEL_BATH_SCREEN_sliding_header', screen['frame_material'], box_mesh(screen['header_bbox_mm']), screen,
        detail='Górna prowadnica dwóch środkowych skrzydeł przesuwnych')
    rollers = screen['rollers']
    add('SEL_BATH_SCREEN_rollers', screen['frame_material'], combine([
        cylinder([x,rollers['center_y_mm']-rollers['depth_mm']/2,rollers['center_z_mm']],
                 [x,rollers['center_y_mm']+rollers['depth_mm']/2,rollers['center_z_mm']], rollers['radius_mm'])
        for x in rollers['x_mm']]), screen)
    for index, handle in enumerate(screen['handles'], 1):
        hx,hz=handle['x_mm'],handle['center_z_mm']
        y=screen['y_mm']+handle['y_offset_mm']; hy=y-handle['projection_mm']
        grip = [cylinder([hx,hy,hz-handle['height_mm']/2], [hx,hy,hz+handle['height_mm']/2], handle['radius_mm'])]
        for z in (hz-handle['height_mm']/2, hz+handle['height_mm']/2):
            grip.append(cylinder([hx,hy,z], [hx,y,z], handle['radius_mm']))
        add(f'SEL_BATH_SCREEN_handle_{index}', screen['frame_material'], combine(grip), screen)

    shower = fixtures['shower']; x,y,z = shower['head_center_mm']; thick=shower['head_thickness_mm']
    add('SEL_BATH_SHOWER_head', shower['material'], combine([
        cylinder([x,y,z-thick/2], [x,y,z+thick/2], shower['head_radius_mm'], segments),
        cylinder([x,y,z+thick/2], [x,y,shower['stem_top_z_mm']], shower['stem_radius_mm'])]), shower,
        detail='Deszczownica sufitowa we wspólnej strefie prysznica i wanny')
    pitch=shower['nozzle_grid_pitch_mm']; nozzles=[]
    for dx in np.arange(-shower['head_radius_mm']+pitch, shower['head_radius_mm'], pitch):
        for dy in np.arange(-shower['head_radius_mm']+pitch, shower['head_radius_mm'], pitch):
            if math.hypot(dx,dy)+shower['nozzle_radius_mm'] < shower['head_radius_mm']:
                nozzles.append(cylinder([x+dx,y+dy,z-thick/2-shower['nozzle_depth_mm']], [x+dx,y+dy,z-thick/2], shower['nozzle_radius_mm']))
    add('SEL_BATH_SHOWER_nozzles', shower['nozzle_material'], combine(nozzles), shower)
    x,y,z=shower['controls_center_mm']
    controls = [cylinder([x,y,z], [x+shower['controls_depth_mm'],y,z], shower['controls_radius_mm']),
                cylinder([x,y,z], [x,y,z+shower['lever_length_mm']], shower['lever_radius_mm'])]
    add('SEL_BATH_SHOWER_mixer', shower['material'], combine(controls), shower)

    wc = fixtures['toilet']
    add('SEL_BATH_WC_bowl', wc['material'], vessel(wc, wc['center_mm'], 'body_profile_mm'), wc,
        detail='Obła miska WC wiszącego')
    add('SEL_BATH_WC_seat', wc['material'], vessel(wc, wc['center_mm'], 'seat_profile_mm', annulus=True), wc,
        detail='Obła deska WC z otworem')
    add('SEL_BATH_WC_service_box', wc['service_box_material'], box_mesh(wc['service_box_bbox_mm']), wc,
        detail='Umowna obudowa stelaża, instalacja niezweryfikowana')
    add('SEL_BATH_WC_flush_plate', wc['flush_material'], box_mesh(wc['flush_plate_bbox_mm']), wc)

    cabinet(fixtures['wc_storage_upper'], 'SEL_BATH_WC_STORAGE_UPPER', 'min_x')
    cabinet(fixtures['wc_storage_side'], 'SEL_BATH_WC_STORAGE_SIDE', 'min_x')

    for accessory in fixtures['accessories']:
        meshes = [box_mesh(bounds) for bounds in accessory.get('boxes', [])]
        meshes.extend(cylinder(item['start_mm'], item['end_mm'], item['radius_mm'])
                      for item in accessory.get('cylinders', []))
        meshes.extend(pipe(item['path_mm'], item['radius_mm'])
                      for item in accessory.get('pipes', []))
        add('SEL_'+accessory['id'], accessory['material'], combine(meshes), accessory,
            detail=accessory['detail'])

    if finishes:
        _build_finishes(finishes, add, box_mesh, cylinder, combine)


def _build_finishes(configuration, add, box_mesh, cylinder, combine):
    """Native closed tile panels, paint, lighting and blinds in the bathroom frame.

    Surface rectangles and cutouts are declarative. Tiling is clipped against the
    source openings before extrusion, so no paint or tile closes the windows
    or entry. No raster image is used to impersonate scene geometry.
    """
    cfg = configuration
    tiling = cfg['tile_layout']

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

    blinds = cfg['blinds']
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
