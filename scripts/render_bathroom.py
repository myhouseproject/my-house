#!/usr/bin/env python3
"""Reproducible Cycles rendering of canonical bathroom geometry.

Run with the optional renderer Python environment (bpy + PyYAML):
  python scripts/render_bathroom.py --scene build/current/scena_lokalna.json \
    --output ../output/bathroom-render --quality preview --camera entrance

No AI images, downloaded room assets, or re-positioned furniture are used. The
renderer reads canonical triangle meshes, applies YAML optical materials, and
adds the explicitly declared cameras and light sources. Structural context is
clipped outside the room to avoid importing the rest of the house.
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
DEFAULT_CONFIG = ROOT / 'modules/06_interior/extracts/bathroom-render.yaml'


def load_configuration(path):
    config = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if config['schema_version'] != 1:
        raise ValueError('Unsupported bathroom renderer schema')
    if config['render']['engine'] != 'CYCLES':
        raise ValueError('Bathroom export requires the declared Cycles renderer')
    for name, quality in ((n, config['render'][n]) for n in ('preview', 'final')):
        if min(quality['resolution']) <= 0 or quality['samples'] <= 0:
            raise ValueError(f'Invalid render quality: {name}')
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
    if scope not in ('bathroom', 'house'):
        raise ValueError('Render scope must be bathroom or house')
    room = config['room_number']
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
            if (part['category'] == 'sufity' and not part.get('bathroom_finish')
                    and part.get('room_number') in rule['house_replaced_ceiling_rooms']):
                continue
            selected.append((part, [to_local_m(point, config['frame'])
                                    for point in part['positions_m']], part['faces']))
            continue
        is_fixture = part.get('room_number') == room and part.get('interior_layer') == 'selected'
        is_window = part['category'] == 'stolarka' and part.get('source_id') in rule['window_source_ids']
        is_ceiling_finish = part.get('room_number') == room and part.get('bathroom_finish')
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
    if not any(part.get('bathroom_fixture') for part, _, _ in selected):
        raise ValueError('No canonical bathroom fixtures found')
    if rule['require_finish_parts'] and not any(part.get('bathroom_finish') for part, _, _ in selected):
        raise ValueError('Bathroom finish geometry missing; rebuild the canonical scene first')
    return selected


def linear_color(srgb):
    def convert(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
    return tuple(convert(float(value)) for value in srgb[:3]) + (1.0,)


def marble_nodes(material, bsdf, config):
    nodes, links = material.node_tree.nodes, material.node_tree.links
    position = nodes.new('ShaderNodeNewGeometry')
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'
    mapping.inputs[1].default_value = config['coordinate_scale']
    links.new(position.outputs['Position'], mapping.inputs[0])
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
    links.new(position.outputs['Position'], micro.inputs['Vector'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = config['bump_strength']
    bump.inputs['Distance'].default_value = config['bump_distance_mm'] / 1000
    links.new(micro.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])


def material_spec(part, config):
    """Keep authored bathroom optics; elsewhere retain canonical color and PBR values."""
    key = part['material']
    if key in config['materials']:
        return config['materials'][key]
    spec = copy.deepcopy(config['materials']['default'])
    if 'color' in part:
        spec['color_srgb'] = part['color'][:3]
    spec.update({key: value for key, value in part.get('pbr', {}).items()
                 if key in ('roughness', 'metallic')})
    if 'emissive' in part.get('pbr', {}):
        spec['emission_color_srgb'] = part['pbr']['emissive']
        spec['emission_strength'] = 1
    return spec


def create_material(bpy, key, config, spec=None):
    spec = spec if spec is not None else config['materials'].get(key, config['materials']['default'])
    material = bpy.data.materials.new(key)
    material.use_nodes = True
    bsdf = material.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = linear_color(spec['color_srgb'])
    mapping = {'roughness': 'Roughness', 'metallic': 'Metallic', 'transmission': 'Transmission Weight',
               'ior': 'IOR', 'coat': 'Coat Weight', 'coat_roughness': 'Coat Roughness',
               'anisotropic': 'Anisotropic', 'emission_strength': 'Emission Strength'}
    for key_name, input_name in mapping.items():
        if key_name in spec:
            bsdf.inputs[input_name].default_value = spec[key_name]
    if 'emission_color_srgb' in spec:
        bsdf.inputs['Emission Color'].default_value = linear_color(spec['emission_color_srgb'])
    if spec.get('marble'):
        marble_nodes(material, bsdf, config['marble_shader'])
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
    for property_name, key in (('max_bounces', 'bounces'), ('diffuse_bounces', 'diffuse_bounces'),
                               ('glossy_bounces', 'glossy_bounces'), ('transmission_bounces', 'transmission_bounces'),
                               ('transparent_max_bounces', 'transparent_bounces'), ('sample_clamp_indirect', 'clamp_indirect')):
        setattr(scene.cycles, property_name, rendering[key])
    scene.render.threads_mode = 'FIXED'; scene.render.threads = rendering['threads']
    scene.render.resolution_x, scene.render.resolution_y = preset['resolution']
    scene.render.resolution_percentage = preset['resolution_percentage']
    scene.render.film_transparent = rendering['transparent_background']
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'
    scene.render.image_settings.color_depth = '16'
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
        if material_key in geometry['smooth_materials']:
            for polygon in mesh.polygons:
                polygon.use_smooth = True
            mesh.set_sharp_from_angle(angle=math.radians(geometry['smooth_angle_degrees']))
        if any(part['name'].endswith(suffix) for suffix in geometry['subdivision_name_suffixes']):
            subdivision = obj.modifiers.new('Render-only surface smoothing', 'SUBSURF')
            subdivision.levels = geometry['subdivision_levels']; subdivision.render_levels = geometry['subdivision_levels']
        elif material_key in geometry['smooth_materials'] or part.get('bathroom_finish'):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, default=ROOT/'build/current/scena_lokalna.json')
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quality', choices=['preview', 'final'], default='preview')
    parser.add_argument('--camera', default='entrance')
    parser.add_argument('--camera-file', type=Path, help='Portal camera JSON in canonical metre/Z-up coordinates')
    parser.add_argument('--scope', choices=['bathroom', 'house'], default='bathroom')
    parser.add_argument('--validate-only', action='store_true', help='Validate source, selection and camera without Blender')
    parser.add_argument('--save-only', action='store_true', help='Save Blender scene without rendering')
    args = parser.parse_args(argv)
    config = load_configuration(args.config)
    if not args.camera_file and args.camera not in config['cameras']:
        parser.error(f'Unknown camera {args.camera}; choose {", ".join(config["cameras"])}')
    source_scene = json.loads(args.scene.read_text(encoding='utf-8'))
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
                          'parts': len(selected), 'resolution': config['render'][args.quality]['resolution']}))
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
        'camera': args.camera, 'quality': args.quality, 'status': config['status'],
        'scope': args.scope, 'portal_camera': portal_camera,
        'camera_file_sha256': hashlib.sha256(args.camera_file.read_bytes()).hexdigest() if args.camera_file else None,
        'lighting_note': 'Bathroom light/material study; other rooms use canonical colors and environment light.',
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
    print(json.dumps({'blend': str(base.with_suffix('.blend')), 'image': str(base.with_suffix('.png')),
                      'manifest': str(base.with_suffix('.json'))}), flush=True)


if __name__ == '__main__':
    # Supports both Python+bpy and `blender --background --python ... -- ARGS`.
    arguments = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None
    main(arguments)
