#!/usr/bin/env python3
"""Reproducible Cycles rendering of canonical interior geometry.

Run with the optional renderer Python environment (bpy + PyYAML):
  python scripts/render_bathroom.py --scene build/current/scena_lokalna.json \
    --output ../output/bathroom-render --quality preview --camera entrance

The renderer reads canonical triangle meshes, applies YAML optical materials
and surface artwork, and adds the explicitly declared cameras and light sources.
Furniture is never repositioned for a render. Structural context is clipped
outside the selected room to avoid importing the rest of the house.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CONFIG = ROOT / 'modules/06_interior/extracts/bathroom-render.yaml'
PROFILE_REGISTRY = ROOT / 'modules/06_interior/model.yaml'


def load_configuration(path, scope='bathroom', registry_path=PROFILE_REGISTRY):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if config['schema_version'] != 1:
        raise ValueError('Unsupported bathroom renderer schema')
    if config['render']['engine'] != 'CYCLES':
        raise ValueError('Bathroom export requires the declared Cycles renderer')
    for name, quality in ((n, config['render'][n]) for n in ('preview', 'final')):
        if min(quality['resolution']) <= 0 or quality['samples'] <= 0:
            raise ValueError(f'Invalid render quality: {name}')
    if scope == 'house':
        config = compose_house_profiles(config, path, registry_path)
    return config


def apply_tile_variant(config, variant, tile_format=None):
    """Apply one declared product texture without changing canonical bathroom geometry."""
    if not variant or variant == 'current':
        config = copy.deepcopy(config)
        config['active_tile_variant'] = 'current'
        return config
    variants = config.get('tile_variants', {})
    if variant not in variants:
        raise ValueError(f'Unknown bathroom tile variant: {variant}')
    if 'bathroom_tile_marble' not in config.get('materials', {}):
        raise ValueError('Selected render profile does not expose bathroom_tile_marble')
    atlas = copy.deepcopy(config.get('tile_texture_atlas', {}))
    if not atlas:
        raise ValueError('Bathroom tile variants require tile_texture_atlas settings')
    result = copy.deepcopy(config)
    selected = copy.deepcopy(variants[variant])
    material = result['materials']['bathroom_tile_marble']
    for key in ('color_srgb', 'roughness', 'coat', 'coat_roughness'):
        if key in selected:
            material[key] = selected[key]
    format_key = tile_format or config.get('active_tile_format', '120x60')
    presets = config.get('tile_format_presets', {})
    if format_key in presets:
        atlas.update(presets[format_key])
    from scripts.prepare_tile_texture import atlas_relative_path
    variant_atlas_rel = atlas_relative_path(variant, format_key)
    variant_atlas_abs = ROOT / variant_atlas_rel
    if not variant_atlas_abs.exists():
        from scripts.prepare_tile_texture import prepare
        prepare(DEFAULT_CONFIG, variant, format_key)
    atlas['path'] = str(variant_atlas_rel)
    material['tile_image_atlas'] = {
        'path': atlas['path'],
        'columns': int(atlas['columns']),
        'rows': int(atlas['rows']),
        'tile_size_mm': list(atlas['tile_size_mm']),
    }
    result['active_tile_variant'] = variant
    result['active_tile_format'] = format_key
    result['active_tile_product'] = {
        key: selected[key] for key in ('label', 'manufacturer', 'product', 'product_url', 'texture_zip_url')
        if key in selected
    }
    result['status'] = 'product_texture_material_study'
    result['provenance'] = copy.deepcopy(result['provenance'])
    result['provenance']['tile_variant'] = result['active_tile_product']
    result['provenance']['tile_format'] = format_key
    return result


def to_canonical_m(point_m, frame):
    """Invert an orthonormal declared room frame without changing scene geometry."""
    return [frame['origin_mm'][i] / 1000 + sum(
        float(point_m[j]) * frame[axis][i]
        for j, axis in enumerate(('x_axis', 'y_axis', 'z_axis'))) for i in range(3)]


def shader_coordinate_transform(render_frame, authored_frame):
    """Keep procedural grain and veins in their authored room coordinates."""
    axes = ('x_axis', 'y_axis', 'z_axis')
    return {
        'rows': [[sum(authored_frame[a][k] * render_frame[b][k] for k in range(3))
                  for b in axes] for a in axes],
        'offset_m': to_local_m([n / 1000 for n in render_frame['origin_mm']], authored_frame),
    }


def compose_house_profiles(config, primary_path, registry_path):
    """Bring every registered room's authored optics into the primary render frame.

    Room presets stay isolated; a portal house view gets all declared room lights
    and materials, instead of lighting only the original main bathroom. Duplicate
    optical keys must agree, so one room cannot silently recolor another.
    """
    config = copy.deepcopy(config)
    registry_path = Path(registry_path)
    registry = yaml.safe_load(registry_path.read_text(encoding='utf-8'))
    paths = [Path(primary_path).resolve()]
    for relative in registry.get('render_profiles', []):
        candidate = (registry_path.parent / relative).resolve()
        if not candidate.is_relative_to(registry_path.parent.resolve()):
            raise ValueError('Render profiles must remain inside the interior module')
        if candidate not in paths:
            paths.append(candidate)
    config['render_profile_sources'] = []
    for index, path in enumerate(paths):
        profile = load_configuration(path)
        config['render_profile_sources'].append({
            'name': path.stem, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'room_numbers': profile.get('room_numbers', [profile.get('room_number')]),
            'provenance': profile['provenance'],
        })
        if index == 0:
            continue
        for key, spec in profile['materials'].items():
            spec = copy.deepcopy(spec)
            if 'image_texture' in spec:
                spec['image_texture']['coordinate_transform'] = shader_coordinate_transform(
                    config['frame'], profile['frame'])
            if spec.get('marble'):
                # Legacy room profiles have one unnamed stone shader. Namespace
                # it on import so a second room retains its own stone palette.
                shader_name = f'{path.stem}__marble'
                config.setdefault('marble_shaders', {})[shader_name] = copy.deepcopy(profile['marble_shader'])
                config['marble_shaders'][shader_name]['coordinate_transform'] = shader_coordinate_transform(
                    config['frame'], profile['frame'])
                spec.pop('marble')
                spec['marble_shader'] = shader_name
            if key in config['materials'] and config['materials'][key] != spec:
                raise ValueError(f'Conflicting authored render material: {key}')
            config['materials'][key] = copy.deepcopy(spec)
        for shader_type in ('marble_shaders', 'wood_shaders', 'surface_shaders'):
            target = config.setdefault(shader_type, {})
            for key, spec in profile.get(shader_type, {}).items():
                spec = copy.deepcopy(spec)
                spec['coordinate_transform'] = shader_coordinate_transform(config['frame'], profile['frame'])
                if key in target and target[key] != spec:
                    raise ValueError(f'Conflicting authored shader: {key}')
                target[key] = copy.deepcopy(spec)
        for key in profile['geometry']['smooth_materials']:
            if key not in config['geometry']['smooth_materials']:
                config['geometry']['smooth_materials'].append(key)
        for room in profile['selection']['house_replaced_ceiling_rooms']:
            if room not in config['selection']['house_replaced_ceiling_rooms']:
                config['selection']['house_replaced_ceiling_rooms'].append(room)
        for original in profile['lights']:
            light = copy.deepcopy(original)
            light['name'] = f'{path.stem}__{original["name"]}'
            for field in ('position_mm', 'target_mm'):
                canonical = to_canonical_m([n / 1000 for n in original[field]], profile['frame'])
                light[field] = [n * 1000 for n in to_local_m(canonical, config['frame'])]
            config['lights'].append(light)
    return config


def to_local_m(point_m, frame):
    relative = [float(point_m[i]) - frame['origin_mm'][i] / 1000 for i in range(3)]
    return [sum(relative[j] * frame[axis][j] for j in range(3))
            for axis in ('x_axis', 'y_axis', 'z_axis')]


def camera_basis(eye, target, up):
    """Camera-to-world columns: screen right, screen up, backward (no roll loss)."""
    def normalized(vector):
        length = math.sqrt(sum(value * value for value in vector))
        if length < 1e-8:
            raise ValueError('Camera eye/target/up vectors must not be coincident or parallel')
        return [value / length for value in vector]

    def cross(a, b):
        return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

    forward = normalized([target[i] - eye[i] for i in range(3)])
    right = normalized(cross(forward, normalized(up)))
    corrected_up = normalized(cross(right, forward))
    return [right, corrected_up, [-value for value in forward]]


def load_camera_file(path, source_scene):
    """Read the public portal camera contract; never execute content from the file."""
    require_canonical_scene(source_scene)
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError('Camera JSON exceeds 64 KiB')
    camera = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(camera, dict):
        raise ValueError('Camera JSON must be an object')
    expected = {'schema_version': 1, 'kind': 'dom-render-camera',
                'coordinate_frame': 'building_local', 'units': 'm', 'up_axis': 'Z'}
    for key, value in expected.items():
        if type(camera.get(key)) is not type(value) or camera.get(key) != value:
            raise ValueError(f'Camera {key} must be {value!r}')
    if camera.get('projection') not in ('perspective', 'orthographic'):
        raise ValueError('Camera projection must be perspective or orthographic')

    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    for key in ('eye', 'target', 'up'):
        vector = camera.get(key)
        if not isinstance(vector, list) or len(vector) != 3 or not all(finite(v) for v in vector):
            raise ValueError(f'Camera {key} must contain three finite numbers')
    camera_basis(camera['eye'], camera['target'], camera['up'])
    resolution = camera.get('resolution')
    if (not isinstance(resolution, list) or len(resolution) != 2
            or not all(type(value) is int and 16 <= value <= 8192 for value in resolution)
            or math.prod(resolution) > 33554432):
        raise ValueError('Camera resolution must be 16–8192 pixels per side and at most 32 megapixels')
    aspect = camera.get('aspect_ratio')
    if not finite(aspect) or aspect <= 0 or not math.isclose(
            aspect, resolution[0] / resolution[1], rel_tol=1 / min(resolution)):
        raise ValueError('Camera aspect_ratio must match resolution')
    if camera['projection'] == 'perspective':
        fov = camera.get('vertical_fov_degrees')
        if not finite(fov) or not 1 <= fov < 170:
            raise ValueError('Camera vertical_fov_degrees must be between 1 and 170')
    else:
        height = camera.get('orthographic_height_m')
        if not finite(height) or not 0 < height <= 10000:
            raise ValueError('Camera orthographic_height_m must be positive and at most 10000')
    vertices = [point for part in source_scene['parts'] for point in part['positions_m']]
    if not vertices:
        raise ValueError('Cannot validate camera against an empty scene')
    lower = [min(point[i] for point in vertices) for i in range(3)]
    upper = [max(point[i] for point in vertices) for i in range(3)]
    margin = 10 * max(1, math.dist(lower, upper))
    for key in ('eye', 'target'):
        if any(not lower[i]-margin <= camera[key][i] <= upper[i]+margin for i in range(3)):
            raise ValueError(f'Camera {key} is outside the canonical scene coordinate range')
    if 'visible_part_names' in camera:
        names = camera['visible_part_names']
        if (not isinstance(names, list) or not 1 <= len(names) <= 4096
                or not all(isinstance(name, str) and 0 < len(name) <= 512 for name in names)
                or len(set(names)) != len(names)):
            raise ValueError('Camera visible_part_names must contain 1–4096 unique part names')
        unknown = set(names) - {part['name'] for part in source_scene['parts']}
        if unknown:
            raise ValueError('Camera references unknown part names; rebuild or use the matching scene release')
    if 'section_height_m' in camera and not finite(camera['section_height_m']):
        raise ValueError('Camera section_height_m must be finite')
    if 'clip_bounds_m' in camera:
        bounds = camera['clip_bounds_m']
        if (not isinstance(bounds, list) or len(bounds) != 2
                or not all(isinstance(corner, list) and len(corner) == 3
                           and all(finite(value) for value in corner) for corner in bounds)
                or not all(bounds[0][i] < bounds[1][i] for i in range(3))):
            raise ValueError('Camera clip_bounds_m must be finite ordered [minimum, maximum] XYZ corners')
    return camera


def apply_portal_camera(config, camera):
    """Return an isolated render config; YAML defaults and source geometry stay intact."""
    config = copy.deepcopy(config)
    spec = copy.deepcopy(config['cameras']['entrance'])
    spec['position_mm'] = [value * 1000 for value in to_local_m(camera['eye'], config['frame'])]
    spec['target_mm'] = [value * 1000 for value in to_local_m(camera['target'], config['frame'])]
    spec['up'] = [sum(camera['up'][j] * config['frame'][axis][j] for j in range(3))
                  for axis in ('x_axis', 'y_axis', 'z_axis')]
    spec['projection'] = camera['projection']
    spec['shift_x'] = spec['shift_y'] = 0
    for key in ('vertical_fov_degrees', 'orthographic_height_m'):
        if key in camera:
            spec[key] = camera[key]
    config['cameras']['portal'] = spec
    for quality in ('preview', 'final'):
        config['render'][quality]['resolution'] = list(camera['resolution'])
        config['render'][quality]['resolution_percentage'] = 100
    return config


def clip_polygon(polygon, axis, boundary, keep_greater):
    """Sutherland–Hodgman clipping; clipped caps are outside the visible room."""
    if not polygon:
        return []
    result = []
    previous = polygon[-1]
    previous_inside = (previous[axis] >= boundary if keep_greater else previous[axis] <= boundary)
    for current in polygon:
        inside = current[axis] >= boundary if keep_greater else current[axis] <= boundary
        if inside != previous_inside:
            fraction = (boundary - previous[axis]) / (current[axis] - previous[axis])
            result.append([previous[j] + fraction * (current[j] - previous[j]) for j in range(3)])
        if inside:
            result.append(current)
        previous, previous_inside = current, inside
    return result


def clip_mesh(vertices, faces, bounds):
    """Crop structural context without moving any canonical surface."""
    lower, upper = bounds
    result_vertices, result_faces = [], []
    for face in faces:
        polygon = [vertices[i] for i in face]
        for axis in range(3):
            polygon = clip_polygon(polygon, axis, lower[axis], True)
            polygon = clip_polygon(polygon, axis, upper[axis], False)
        if len(polygon) >= 3:
            start = len(result_vertices)
            result_vertices.extend(polygon)
            result_faces.extend((start, start+i, start+i+1) for i in range(1, len(polygon)-1))
    return result_vertices, result_faces


def apply_portal_visibility(selected, camera, config):
    """Replay portal visibility/cutaways on copies, without altering canonical meshes."""
    if 'visible_part_names' in camera:
        names = set(camera['visible_part_names'])
        selected = [item for item in selected if item[0]['name'] in names]
    if not selected:
        raise ValueError('Portal camera has no visible renderable parts in the chosen scope')
    bounds = camera.get('clip_bounds_m')
    if bounds is not None:
        corners = [to_local_m(point, config['frame']) for point in itertools.product(
            *[(bounds[0][i], bounds[1][i]) for i in range(3)])]
        lower = [min(corner[i] for corner in corners) for i in range(3)]
        upper = [max(corner[i] for corner in corners) for i in range(3)]
    else:
        lower = [min(point[i] for _, vertices, _ in selected for point in vertices) for i in range(3)]
        upper = [max(point[i] for _, vertices, _ in selected for point in vertices) for i in range(3)]
    if 'section_height_m' in camera:
        # The declared room frame preserves canonical Z. Assert before applying a horizontal section.
        if config['frame']['z_axis'] != [0, 0, 1]:
            raise ValueError('Horizontal portal sections require a Z-preserving render frame')
        upper[2] = min(upper[2], camera['section_height_m'] - config['frame']['origin_mm'][2]/1000)
    if bounds is None and 'section_height_m' not in camera:
        return selected
    result = []
    for part, vertices, faces in selected:
        if any(max(v[axis] for v in vertices) < lower[axis]
               or min(v[axis] for v in vertices) > upper[axis] for axis in range(3)):
            continue
        if not all(lower[i] <= vertex[i] <= upper[i] for vertex in vertices for i in range(3)):
            vertices, faces = clip_mesh(vertices, faces, [lower, upper])
        if faces:
            result.append((part, vertices, faces))
    if not result:
        raise ValueError('Portal section/crop excludes all renderable geometry')
    return result


def require_canonical_scene(scene):
    if (scene.get('units') != 'm' or scene.get('up_axis') != 'Z'
            or scene.get('coordinate_frame') != 'building_local'):
        raise ValueError('Expected canonical building_local metre/Z-up scene, not map coordinates or a transformed GLB')


def select_parts(scene, config, scope='bathroom', visible_part_names=None):
    require_canonical_scene(scene)
    selected = []
    if scope not in ('bathroom', 'room', 'house'):
        raise ValueError('Render scope must be room, bathroom or house')
    rooms = set(config.get('room_numbers', [config.get('room_number')]))
    rule = config['selection']
    crop_bounds = [[coordinate / 1000 for coordinate in corner]
                   for corner in rule['crop_bounds_mm']]
    explicit_names = set(visible_part_names) if visible_part_names is not None else None
    for part in scene['parts']:
        if scope == 'house' and explicit_names is not None:
            # A portal view can deliberately show the base floor, blocks or ceilings.
            # Replay its mesh selection rather than applying another variant on top.
            if part['name'] in explicit_names and part['positions_m'] and part['faces']:
                selected.append((part, [to_local_m(point, config['frame'])
                                        for point in part['positions_m']], part['faces']))
            continue
        if part.get('superseded_by_finish') or part.get('interior_layer') == 'blocks':
            continue
        if any(part['name'].endswith(suffix) for suffix in rule['exclude_name_suffixes']):
            continue
        if not part['positions_m'] or not part['faces']:
            continue
        if scope == 'house':
            if (part['category'] in rule['house_excluded_categories']
                    or any(part['category'].startswith(prefix)
                           for prefix in rule['house_excluded_category_prefixes'])):
                continue
            if (part['category'] == 'sufity' and not is_interior_finish(part)
                    and part.get('room_number') in rule['house_replaced_ceiling_rooms']):
                continue
            selected.append((part, [to_local_m(point, config['frame'])
                                    for point in part['positions_m']], part['faces']))
            continue
        is_fixture = part.get('room_number') in rooms and (
            part.get('interior_layer') == 'selected' or is_interior_fixture(part))
        is_window = part['category'] == 'stolarka' and part.get('source_id') in rule['window_source_ids']
        is_ceiling_finish = part.get('room_number') in rooms and is_interior_finish(part)
        is_structure = part['category'] in rule['structural_categories']
        if not (is_fixture or is_window or is_ceiling_finish or is_structure):
            continue
        vertices = [to_local_m(point, config['frame']) for point in part['positions_m']]
        faces = part['faces']
        if is_structure:
            if any(max(v[axis] for v in vertices) < crop_bounds[0][axis]
                   or min(v[axis] for v in vertices) > crop_bounds[1][axis] for axis in range(3)):
                continue
            vertices, faces = clip_mesh(vertices, faces, crop_bounds)
        if faces:
            selected.append((part, vertices, faces))
    if scope == 'house':
        if not selected:
            raise ValueError('No canonical house geometry found')
        return selected
    if not any(is_interior_fixture(part) for part, _, _ in selected):
        raise ValueError('No canonical interior fixtures found')
    if rule['require_finish_parts'] and not any(is_interior_finish(part) for part, _, _ in selected):
        raise ValueError('Interior finish geometry missing; rebuild the canonical scene first')
    return selected


def is_interior_finish(part):
    return bool(part.get('interior_finish') or part.get('bathroom_finish'))


def is_interior_fixture(part):
    return bool(part.get('interior_fixture') or part.get('bedroom_fixture') or part.get('bathroom_fixture'))


def linear_color(srgb):
    def convert(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    return tuple(convert(float(value)) for value in srgb[:3]) + (1.0,)


def texture_position(material, config):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    geometry = nodes.new('ShaderNodeNewGeometry')
    position = geometry.outputs['Position']
    transform = config.get('coordinate_transform')
    if transform:
        combined = nodes.new('ShaderNodeCombineXYZ')
        for index, row in enumerate(transform['rows']):
            dot = nodes.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
            links.new(position, dot.inputs[0]); dot.inputs[1].default_value = row
            links.new(dot.outputs['Value'], combined.inputs[index])
        offset = nodes.new('ShaderNodeVectorMath'); offset.operation = 'ADD'
        links.new(combined.outputs['Vector'], offset.inputs[0])
        offset.inputs[1].default_value = transform['offset_m']
        position = offset.outputs['Vector']
    return position


def marble_nodes(material, bsdf, config):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = texture_position(material, config)
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = config['coordinate_scale']
    links.new(position, mapping.inputs[0])
    cloud = nodes.new('ShaderNodeTexNoise')
    cloud.inputs['Scale'].default_value = config['cloud_scale']
    cloud.inputs['Detail'].default_value = config['cloud_detail']
    cloud.inputs['Roughness'].default_value = config['cloud_roughness']
    links.new(mapping.outputs['Vector'], cloud.inputs['Vector'])
    clouds = nodes.new('ShaderNodeValToRGB')
    clouds.color_ramp.elements[0].color = linear_color(config['cloud_color_dark_srgb'])
    clouds.color_ramp.elements[1].color = linear_color(config['cloud_color_light_srgb'])
    links.new(cloud.outputs['Fac'], clouds.inputs[0])
    wave = nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'BANDS'; wave.bands_direction = 'DIAGONAL'; wave.wave_profile = 'SIN'
    for key, source in (('Scale', 'wave_scale'), ('Distortion', 'wave_distortion'),
                        ('Detail', 'wave_detail'), ('Detail Scale', 'wave_detail_scale'),
                        ('Detail Roughness', 'wave_detail_roughness')):
        wave.inputs[key].default_value = config[source]
    links.new(mapping.outputs['Vector'], wave.inputs['Vector'])
    veins = nodes.new('ShaderNodeValToRGB')
    ramp = veins.color_ramp
    for index, (position_value, color) in enumerate(config['vein_ramp']):
        element = ramp.elements[index] if index < 2 else ramp.elements.new(position_value)
        element.position = position_value; element.color = linear_color(color)
    ramp.interpolation = 'EASE'
    links.new(wave.outputs['Fac'], veins.inputs[0])
    mix = nodes.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = config['cloud_blend']
    links.new(veins.outputs['Color'], mix.inputs[1]); links.new(clouds.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs[0], bsdf.inputs['Base Color'])
    micro = nodes.new('ShaderNodeTexNoise')
    micro.inputs['Scale'].default_value = config['micro_scale']
    links.new(position, micro.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = config['bump_strength']
    bump.inputs['Distance'].default_value = config['bump_distance_mm'] / 1000
    links.new(micro.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])


def material_spec(part, config):
    """Keep authored optics and align product tile atlases with the real grout grid."""
    key = part['material']
    if key in config['materials']:
        spec = copy.deepcopy(config['materials'][key])
        atlas = spec.get('tile_image_atlas')
        if (atlas and part.get('bathroom_finish') and part.get('finish_uv_axes')
                and part['name'].endswith('_tiles')):
            u, v = part['finish_uv_axes']
            grid = part.get('finish_grid_origin_uv_mm', [0, 0])
            origin = [0.0, 0.0, 0.0]
            origin[u], origin[v] = float(grid[0]), float(grid[1])
            axes = [[0, 0, 0], [0, 0, 0]]
            axes[0][u] = 1
            axes[1][v] = 1
            spec.pop('marble', None)
            spec.pop('marble_shader', None)
            spec.pop('tile_image_atlas', None)
            spec['image_texture'] = {
                'path': atlas['path'],
                'origin_mm': origin,
                'axes': axes,
                'size_mm': [
                    float(atlas['tile_size_mm'][0]) * int(atlas['columns']),
                    float(atlas['tile_size_mm'][1]) * int(atlas['rows']),
                ],
                'interpolation': 'Linear',
                'extension': 'REPEAT',
            }
        return spec
    spec = copy.deepcopy(config['materials']['default'])
    if 'color' in part:
        spec['color_srgb'] = part['color'][:3]
    spec.update({key: value for key, value in part.get('pbr', {}).items()
                 if key in ('roughness', 'metallic')})
    if 'emissive' in part.get('pbr', {}):
        spec['emission_color_srgb'] = part['pbr']['emissive']
        spec['emission_strength'] = 1
    return spec


def wood_nodes(material, bsdf, config):
    """Subtle directional oak grain; physical flutes remain canonical geometry."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = texture_position(material, config)
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = config['coordinate_scale']
    links.new(position, mapping.inputs[0])
    grain = nodes.new('ShaderNodeTexNoise')
    grain.inputs['Scale'].default_value = config['grain_scale']
    grain.inputs['Detail'].default_value = config['grain_detail']
    grain.inputs['Roughness'].default_value = config['grain_roughness']
    links.new(mapping.outputs['Vector'], grain.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = linear_color(config['color_dark_srgb'])
    ramp.color_ramp.elements[1].color = linear_color(config['color_light_srgb'])
    links.new(grain.outputs['Fac'], ramp.inputs[0])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = config['bump_strength']
    bump.inputs['Distance'].default_value = config['bump_distance_mm'] / 1000
    links.new(grain.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])


def surface_nodes(material, bsdf, config):
    """Fine, scale-declared textile or mineral variation without altering meshes."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = texture_position(material, config)
    cloud = nodes.new('ShaderNodeTexNoise')
    for input_name, key in (('Scale', 'color_scale'), ('Detail', 'detail'), ('Roughness', 'roughness')):
        cloud.inputs[input_name].default_value = config[key]
    links.new(position, cloud.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = linear_color(config['color_dark_srgb'])
    ramp.color_ramp.elements[1].color = linear_color(config['color_light_srgb'])
    links.new(cloud.outputs['Fac'], ramp.inputs[0])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    micro = nodes.new('ShaderNodeTexNoise')
    micro.inputs['Scale'].default_value = config['micro_scale']
    micro.inputs['Detail'].default_value = config['detail']
    links.new(position, micro.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = config['bump_strength']
    bump.inputs['Distance'].default_value = config['bump_distance_mm'] / 1000
    links.new(micro.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])


def image_texture_path(spec):
    """Only project-local artwork can become a material texture."""
    path = (ROOT / spec['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Material image texture must remain inside the project')
    if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
        raise ValueError('Material image texture must use PNG, JPEG or WebP')
    return path


def image_texture_nodes(bpy, material, bsdf, config):
    """Project artwork in authored room coordinates, also in whole-house views."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = texture_position(material, config)
    relative = nodes.new('ShaderNodeVectorMath'); relative.operation = 'SUBTRACT'
    links.new(position, relative.inputs[0])
    relative.inputs[1].default_value = [n / 1000 for n in config['origin_mm']]
    combined = nodes.new('ShaderNodeCombineXYZ')
    for index, axis in enumerate(config['axes']):
        dot = nodes.new('ShaderNodeVectorMath'); dot.operation = 'DOT_PRODUCT'
        links.new(relative.outputs['Vector'], dot.inputs[0])
        dot.inputs[1].default_value = [n * 1000 / config['size_mm'][index] for n in axis]
        links.new(dot.outputs['Value'], combined.inputs[index])
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = bpy.data.images.load(str(image_texture_path(config)), check_existing=True)
    texture.image.colorspace_settings.name = 'sRGB'
    texture.image.pack()
    texture.interpolation = config['interpolation']
    texture.extension = config['extension']
    links.new(combined.outputs['Vector'], texture.inputs['Vector'])
    links.new(texture.outputs['Color'], bsdf.inputs['Base Color'])


def setup_architectural_glass(bpy, material, bsdf):
    """ArchViz thin-glass shader: Fresnel reflection for camera rays, 100% transparent for all light transport."""
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    lp = nodes.new('ShaderNodeLightPath')
    fresnel = nodes.new('ShaderNodeFresnel')
    fresnel.inputs['IOR'].default_value = 1.25
    glossy = nodes.new('ShaderNodeBsdfGlossy')
    glossy.inputs['Roughness'].default_value = 0.015
    glossy.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    trans = nodes.new('ShaderNodeBsdfTransparent')
    trans.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
    mix_refl = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], mix_refl.inputs['Fac'])
    links.new(trans.outputs['BSDF'], mix_refl.inputs[1])
    links.new(glossy.outputs['BSDF'], mix_refl.inputs[2])
    mix_cam = nodes.new('ShaderNodeMixShader')
    links.new(lp.outputs['Is Camera Ray'], mix_cam.inputs['Fac'])
    links.new(trans.outputs['BSDF'], mix_cam.inputs[1])
    links.new(mix_refl.outputs['Shader'], mix_cam.inputs[2])
    out = nodes.new('ShaderNodeOutputMaterial')
    links.new(mix_cam.outputs['Shader'], out.inputs['Surface'])


def create_material(bpy, key, config, spec=None):
    spec = spec if spec is not None else config['materials'].get(key, config['materials']['default'])
    material = bpy.data.materials.new(key)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = linear_color(spec['color_srgb'])
    mapping = {'roughness': 'Roughness', 'metallic': 'Metallic', 'transmission': 'Transmission Weight',
               'ior': 'IOR', 'coat': 'Coat Weight', 'coat_roughness': 'Coat Roughness',
               'anisotropic': 'Anisotropic', 'emission_strength': 'Emission Strength',
               'sheen': 'Sheen Weight', 'sheen_roughness': 'Sheen Roughness'}
    for key_name, input_name in mapping.items():
        if key_name in spec:
            bsdf.inputs[input_name].default_value = spec[key_name]
    if 'emission_color_srgb' in spec:
        bsdf.inputs['Emission Color'].default_value = linear_color(spec['emission_color_srgb'])
    if spec.get('marble'):
        marble_nodes(material, bsdf, config['marble_shader'])
    elif 'marble_shader' in spec:
        marble_nodes(material, bsdf, config['marble_shaders'][spec['marble_shader']])
    if 'wood_shader' in spec:
        wood_nodes(material, bsdf, config['wood_shaders'][spec['wood_shader']])
    if 'surface_shader' in spec:
        surface_nodes(material, bsdf, config['surface_shaders'][spec['surface_shader']])
    if 'image_texture' in spec:
        image_texture_nodes(bpy, material, bsdf, spec['image_texture'])
    if spec.get('transmission', 0) > 0.5 or key in ('bathroom_glass', 'szklo', 'bathroom_lamp_glass') or 'glass' in key:
        setup_architectural_glass(bpy, material, bsdf)
    return material


def orient_at(obj, point_mm):
    from mathutils import Vector
    target = Vector([value / 1000 for value in point_mm])
    obj.rotation_euler = (target - obj.location).to_track_quat('-Z', 'Y').to_euler()


def prepare_scene(bpy, config, selected, quality, camera_name):
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.unit_settings.length_unit = 'METERS'
    rendering = config['render']; preset = rendering[quality]
    scene.render.engine = rendering['engine']
    scene.cycles.device = rendering['device']
    scene.cycles.samples = preset['samples']; scene.cycles.seed = rendering['seed']
    scene.cycles.use_denoising = rendering['denoise']
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = rendering['adaptive_threshold']
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    for property_name, key in (('max_bounces', 'bounces'), ('diffuse_bounces', 'diffuse_bounces'),
                               ('glossy_bounces', 'glossy_bounces'), ('transmission_bounces', 'transmission_bounces'),
                               ('transparent_max_bounces', 'transparent_bounces'), ('sample_clamp_indirect', 'clamp_indirect')):
        setattr(scene.cycles, property_name, rendering[key])
    scene.render.threads_mode = 'FIXED'; scene.render.threads = rendering['threads']
    scene.render.resolution_x, scene.render.resolution_y = preset['resolution']
    scene.render.resolution_percentage = preset['resolution_percentage']
    scene.render.film_transparent = rendering['transparent_background']
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '8'
    for key in ('view_transform', 'look', 'exposure', 'gamma'):
        setattr(scene.view_settings, key, rendering[key])
    materials = {}
    geometry = config['geometry']
    for part, vertices, faces in selected:
        mesh = bpy.data.meshes.new(part['name'])
        mesh.from_pydata(vertices, [], faces); mesh.update()
        obj = bpy.data.objects.new(part['name'], mesh); scene.collection.objects.link(obj)
        material_key = part['material']
        spec = material_spec(part, config)
        cache_key = (material_key, json.dumps(spec, sort_keys=True))
        if cache_key not in materials:
            materials[cache_key] = create_material(bpy, material_key, config, spec)
        obj.data.materials.append(materials[cache_key])
        obj['canonical_name'] = part['name']; obj['source_id'] = part.get('source_id', '')
        obj['design_status'] = part.get('design_status', part.get('status', 'project'))
        obj['canonical_geometry'] = True
        flat_metal_parts = {
            'SEL_BATH_SCREEN_frame', 'SEL_BATH_SCREEN_sliding_header',
            'SEL_BATH_WC_flush_plate', 'FIN_BATH_W05_BLIND_slats',
            'FIN_BATH_W06_BLIND_slats', 'FIN_BATH_W05_BLIND_headrail',
            'FIN_BATH_W06_BLIND_headrail', 'SEL_BATH_LINEAR_DRAIN'
        }
        if part['name'] in flat_metal_parts:
            for polygon in mesh.polygons:
                polygon.use_smooth = False
        elif material_key in geometry['smooth_materials']:
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            mesh.set_sharp_from_angle(angle=math.radians(geometry['smooth_angle_degrees']))
        if any(part['name'].endswith(suffix) for suffix in geometry['subdivision_name_suffixes']):
            subdivision = obj.modifiers.new('Render-only surface smoothing', 'SUBSURF')
            subdivision.levels = geometry['subdivision_levels']; subdivision.render_levels = geometry['subdivision_levels']
        elif (material_key in geometry['smooth_materials'] or is_interior_finish(part)) and part['name'] not in flat_metal_parts:
            if not config['materials'].get(material_key, {}).get('emission_strength'):
                bevel = obj.modifiers.new('Render-only edge finish', 'BEVEL')
                bevel.width = geometry['bevel_width_mm'] / 1000
                bevel.segments = geometry['bevel_segments']; bevel.limit_method = 'ANGLE'
                bevel.angle_limit = math.radians(geometry['bevel_angle_degrees'])
                bevel.harden_normals = True
    world = bpy.data.worlds.new('Bathroom daylight')
    world.use_nodes = True; scene.world = world
    background = world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value = linear_color(config['world']['color_srgb'])
    background.inputs['Strength'].default_value = config['world']['strength']
    for light_spec in config['lights']:
        data = bpy.data.lights.new(light_spec['name'], type=light_spec['type'])
        data.energy = light_spec['energy_w']; data.color = linear_color(light_spec['color_srgb'])[:3]
        if light_spec['type'] == 'AREA':
            data.shape = 'RECTANGLE'; data.size, data.size_y = [value / 1000 for value in light_spec['size_mm']]
        light = bpy.data.objects.new(light_spec['name'], data); scene.collection.objects.link(light)
        for visibility in ('visible_camera', 'visible_glossy', 'visible_transmission'):
            setattr(light, visibility, light_spec.get(visibility, True))
        light.location = [value / 1000 for value in light_spec['position_mm']]
        orient_at(light, light_spec['target_mm'])
    for name, spec in config['cameras'].items():
        data = bpy.data.cameras.new(name)
        data.lens = spec['lens_mm']; data.sensor_width = spec['sensor_width_mm']
        data.shift_x = spec['shift_x']; data.shift_y = spec['shift_y']
        data.clip_start = spec['clip_start_mm'] / 1000; data.clip_end = spec['clip_end_mm'] / 1000
        camera = bpy.data.objects.new('Camera_'+name, data); scene.collection.objects.link(camera)
        camera.location = [value / 1000 for value in spec['position_mm']]
        if 'up' in spec:
            from mathutils import Matrix
            basis = camera_basis(spec['position_mm'], spec['target_mm'], spec['up'])
            camera.rotation_euler = Matrix(basis).transposed().to_quaternion().to_euler()
        else:
            orient_at(camera, spec['target_mm'])
        if spec.get('projection') == 'orthographic':
            data.type = 'ORTHO'
            data.sensor_fit = 'VERTICAL'
            data.ortho_scale = spec['orthographic_height_m']
        elif 'vertical_fov_degrees' in spec:
            data.sensor_fit = 'VERTICAL'
            data.lens = data.sensor_height / (2 * math.tan(math.radians(spec['vertical_fov_degrees']) / 2))
        if name == camera_name:
            scene.camera = camera
    scene['render_status'] = config['status']
    scene['material_provenance'] = json.dumps(config['provenance'], ensure_ascii=False)
    scene['note'] = 'Canonical room geometry; optional render-only smoothing; conceptual procedural finishes.'
    return scene


def apply_post_denoise(image_path: Path):
    """Apply high-quality edge-preserving non-local means denoising if cv2 is available."""
    try:
        import cv2
        img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            return
        if len(img.shape) == 3 and img.shape[2] == 4:
            bgr = img[:, :, :3]
            alpha = img[:, :, 3]
            denoised_bgr = cv2.fastNlMeansDenoisingColored(
                bgr, None, h=8.0, hColor=8.0, templateWindowSize=7, searchWindowSize=21
            )
            denoised = cv2.merge([denoised_bgr, alpha])
        elif len(img.shape) == 3 and img.shape[2] == 3:
            denoised = cv2.fastNlMeansDenoisingColored(
                img, None, h=8.0, hColor=8.0, templateWindowSize=7, searchWindowSize=21
            )
        else:
            denoised = cv2.fastNlMeansDenoising(img, None, h=8.0, templateWindowSize=7, searchWindowSize=21)
        cv2.imwrite(str(image_path), denoised)
    except Exception as exc:
        print(f'Note: post-render denoise skipped: {exc}', file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, default=ROOT/'build/current/scena_lokalna.json')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quality', choices=['preview', 'final'], default='preview')
    parser.add_argument('--tile-variant', default='current',
                        help='Declared R07 product texture variant; current keeps the authored procedural study')
    parser.add_argument('--tile-format', '--format', default='120x60',
                        choices=['120x60', '120x120', '120x280'],
                        help='Tile format preset (120x60, 120x120, 120x280)')
    parser.add_argument('--camera', default='entrance')
    parser.add_argument('--camera-file', type=Path, help='Portal camera JSON in canonical metre/Z-up coordinates')
    parser.add_argument('--scope', choices=['room', 'bathroom', 'house'], default='bathroom')
    parser.add_argument('--validate-only', action='store_true', help='Validate source, selection and camera without Blender')
    parser.add_argument('--save-only', action='store_true', help='Save Blender scene without rendering')
    args = parser.parse_args(argv)
    config = load_configuration(args.config, args.scope)
    config = apply_tile_variant(config, args.tile_variant, args.tile_format)
    if not args.camera_file and args.camera not in config['cameras']:
        parser.error(f'Unknown camera {args.camera}; choose {", ".join(config["cameras"])}')
    source_scene = json.loads(args.scene.read_text(encoding='utf-8'))
    if args.tile_format and args.tile_format != '120x60':
        try:
            from project_config import load_interior_model
            from bathroom_geometry import build_bathroom
            interior_model = load_interior_model()
            fin_cfg = copy.deepcopy(interior_model['bathroom_finishes'])
            fin_cfg['tile_layout']['active_format'] = args.tile_format
            if 'tile_format_presets' in fin_cfg and args.tile_format in fin_cfg['tile_format_presets']:
                fin_cfg['tile_layout'].update(fin_cfg['tile_format_presets'][args.tile_format])
            regenerated_finish_parts = []
            def collect_part(name, category, material, mesh, source, assumed, note, source_id, extras):
                if extras.get('bathroom_finish'):
                    regenerated_finish_parts.append({
                        'name': name, 'category': category, 'material': material,
                        'source_id': source_id, 'positions_m': mesh.vertices.tolist(),
                        'faces': mesh.faces.tolist(), **extras
                    })
            build_bathroom(interior_model['bathroom'], collect_part, finishes=fin_cfg)
            kept_parts = [p for p in source_scene['parts'] if not p.get('bathroom_finish')]
            source_scene = {**source_scene, 'parts': kept_parts + regenerated_finish_parts}
        except Exception as exc:
            print(f'Warning: could not regenerate finish parts for format {args.tile_format}: {exc}', file=sys.stderr)
    portal_camera = None
    if args.camera_file:
        portal_camera = load_camera_file(args.camera_file, source_scene)
        config = apply_portal_camera(config, portal_camera)
        args.camera = 'portal'
    selected = select_parts(source_scene, config, args.scope,
                            portal_camera.get('visible_part_names') if portal_camera else None)
    if portal_camera:
        selected = apply_portal_visibility(selected, portal_camera, config)
    if args.validate_only:
        print(json.dumps({'valid': True, 'scope': args.scope, 'camera': args.camera,
                          'parts': len(selected), 'resolution': config['render'][args.quality]['resolution'],
                          'tile_variant': config.get('active_tile_variant', 'current')}))
        return
    import bpy
    scene = prepare_scene(bpy, config, selected, args.quality, args.camera)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    base = output/f'{args.scope}-{args.camera}-{args.quality}'
    scene.render.filepath = str(base.with_suffix('.png'))
    manifest = {
        'schema_version': 1, 'renderer': 'Blender Cycles', 'blender_version': bpy.app.version_string,
        'scene_sha256': hashlib.sha256(args.scene.read_bytes()).hexdigest(),
        'config_sha256': hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'resolved_config_sha256': hashlib.sha256(json.dumps(config, sort_keys=True).encode('utf-8')).hexdigest(),
        'render_profile_sources': config.get('render_profile_sources', []),
        'camera': args.camera, 'quality': args.quality, 'status': config['status'],
        'tile_variant': config.get('active_tile_variant', 'current'),
        'tile_product': config.get('active_tile_product'),
        'scope': args.scope, 'portal_camera': portal_camera,
        'camera_file_sha256': hashlib.sha256(args.camera_file.read_bytes()).hexdigest() if args.camera_file else None,
        'lighting_note': ('All registered room profiles contribute authored materials and lights; other rooms use canonical colors.'
                          if args.scope == 'house' else 'Room light/material study using the selected declared profile.'),
        'provenance': config['provenance'], 'canonical_coordinate_transform': config['frame'],
        'render_geometry_modifiers': config['geometry'],
        'parts': [{'name': p['name'], 'source_id': p.get('source_id'), 'material': p['material'],
                   'triangles': len(f)} for p, _, f in selected],
    }
    base.with_suffix('.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(base.with_suffix('.blend')), compress=True)
    print(f'Rendering {len(selected)} canonical parts with {bpy.app.version_string}: {base}', flush=True)
    if not args.save_only:
        bpy.ops.render.render(write_still=True)
        if config['render'].get('denoise', True):
            apply_post_denoise(Path(scene.render.filepath))
    print(json.dumps({'blend': str(base.with_suffix('.blend')), 'image': str(base.with_suffix('.png')),
                      'manifest': str(base.with_suffix('.json'))}), flush=True)


if __name__ == '__main__':
    # Supports both Python+bpy and `blender --background --python ... -- ARGS`.
    arguments = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None
    main(arguments)
