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


def build_bathroom(configuration, emit):
    """Emit separate blocks and selected fixtures through the canonical mesh contract."""
    if not configuration:
        return
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
        emit(name, 'wnetrze_bloki' if layer == 'blocks' else 'wnetrze_elementy', material, result,
             source, True, detail or fixture.get('role', ''), fixture['id'], {
                 'room_number': cfg['room_number'], 'interior_layer': layer,
                 'bathroom_fixture': fixture['id'], 'provenance': cfg['provenance'],
                 'design_status': cfg['status'], 'product_status': 'generic_concept_not_selected_product',
                 'material_status': 'neutral_preview_no_tile_selection',
                 'local_bathroom_frame': frame,
             })

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

    lining = fixtures['shower_lining']
    (x0,y0,z0),(x1,y1,z1) = lining['bbox_mm']
    ny0,ny1 = lining['niche_y_mm']; nz0,nz1 = lining['niche_z_mm']; back = lining['back_x_mm']
    # Five disjoint solids describe a recessed shelf entirely inside the room.
    # The structural wall and its source geometry are never modified.
    lining_pieces = [box_mesh([[back,y0,z0],[x1,y1,z1]]),
                     box_mesh([[x0,y0,z0],[back,y1,nz0]]),
                     box_mesh([[x0,y0,nz1],[back,y1,z1]]),
                     box_mesh([[x0,y0,nz0],[back,ny0,nz1]]),
                     box_mesh([[x0,ny1,nz0],[back,y1,nz1]])]
    add('SEL_BATH_SHOWER_niche_lining', lining['material'], combine(lining_pieces), lining,
        detail=lining['note'])

    for accessory in fixtures['accessories']:
        meshes = [box_mesh(bounds) for bounds in accessory.get('boxes', [])]
        meshes.extend(cylinder(item['start_mm'], item['end_mm'], item['radius_mm'])
                      for item in accessory.get('cylinders', []))
        meshes.extend(pipe(item['path_mm'], item['radius_mm'])
                      for item in accessory.get('pipes', []))
        add('SEL_'+accessory['id'], accessory['material'], combine(meshes), accessory,
            detail=accessory['detail'])
