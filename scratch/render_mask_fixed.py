import bpy
from mathutils import Vector

def render_masks():
    blend_path = "/tmp/test_baseline/bathroom-entrance-preview.blend"
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    scene = bpy.context.scene

    colors = {
        'floor': (1.0, 0.0, 0.0, 1.0),      # Red
        'wall_left': (0.0, 1.0, 0.0, 1.0),  # Green
        'wall_mid': (0.0, 0.0, 1.0, 1.0),   # Blue
        'wall_right': (1.0, 1.0, 0.0, 1.0), # Yellow
        'ceiling': (0.0, 1.0, 1.0, 1.0),    # Cyan
    }

    mats = {}
    for name, col in colors.items():
        mat = bpy.data.materials.new(f'Mask_{name}')
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()
        emit = nodes.new('ShaderNodeEmission')
        emit.inputs['Color'].default_value = col
        emit.inputs['Strength'].default_value = 1.0
        out = nodes.new('ShaderNodeOutputMaterial')
        mat.node_tree.links.new(emit.outputs['Emission'], out.inputs['Surface'])
        mats[name] = mat

    # Only shower screen glass panels are hidden so camera rays pass through to the floor & walls behind
    shower_glass = [
        'sel_bath_screen_fixed_left',
        'sel_bath_screen_door_left',
        'sel_bath_screen_door_right',
        'sel_bath_screen_fixed_right',
    ]

    for obj in scene.objects:
        if obj.type != 'MESH':
            continue
        obj_name = obj.name.lower()
        if any(k in obj_name for k in shower_glass):
            obj.hide_render = True
            continue
        else:
            obj.hide_render = False

    # Setup world & lights
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get('Background')
    if bg:
        bg.inputs['Strength'].default_value = 0.0

    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.data.energy = 0.0

    scene.cycles.samples = 1
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.exposure = 0.0
    scene.render.resolution_x = 2000
    scene.render.resolution_y = 1600

    cameras = {
        'entrance': scene.objects.get('Camera_entrance'),
        'reverse': scene.objects.get('Camera_reverse')
    }

    for cam_name, cam_obj in cameras.items():
        if not cam_obj:
            print(f"Warning: camera {cam_name} not found")
            continue
        scene.camera = cam_obj

        # Assign materials based on camera view
        for obj in scene.objects:
            if obj.type != 'MESH' or obj.hide_render:
                continue
            name = obj.name.lower()

            # 1. Floor & Ceiling
            if 'floor' in name or 'linear_drain' in name:
                cat = 'floor'
            elif 'ceiling' in name or 'downlights' in name:
                cat = 'ceiling'
            elif cam_name == 'entrance':
                # ENTRANCE VIEW: looking towards South (Y=4.25)
                # East (X ~ 0) is on the LEFT of the camera -> wall_left
                # West (X ~ 2.6) is on the RIGHT of the camera -> wall_right
                # South (Y ~ 4.25) is straight AHEAD -> wall_mid
                if 'east' in name or 'vanity' in name or 'basin' in name or 'mirror' in name or 'pendant' in name or '07' in name:
                    cat = 'wall_left'
                elif 'west' in name or 'wc' in name or 'bidet' in name or 'radiator' in name or 'shower' in name or 'dr06' in name or '09' in name:
                    cat = 'wall_right'
                elif 'south' in name or 'tub' in name or 'w05' in name or 'w06' in name or '08' in name or 'screen' in name:
                    cat = 'wall_mid'
                else:
                    # fallback by coordinates
                    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                    xs = [b.x for b in bb]; ys = [b.y for b in bb]; zs = [b.z for b in bb]
                    avg_x = sum(xs)/len(xs); avg_y = sum(ys)/len(ys); avg_z = sum(zs)/len(zs)
                    if avg_z < 0.02:
                        cat = 'floor'
                    elif avg_z > 2.80:
                        cat = 'ceiling'
                    elif avg_x < 1.0:
                        cat = 'wall_left'
                    elif avg_x > 1.8:
                        cat = 'wall_right'
                    else:
                        cat = 'wall_mid'
            else:
                # REVERSE VIEW: looking towards North (Y=0.0)
                # Keep physical room identity matching entrance view:
                # East (vanity wall) is 'wall_left'
                # West (WC wall) is 'wall_right'
                # North (entrance wall) is 'wall_mid'
                if 'east' in name or 'vanity' in name or 'basin' in name or 'mirror' in name or 'pendant' in name or '07' in name:
                    cat = 'wall_left'
                elif 'west' in name or 'wc' in name or 'bidet' in name or 'radiator' in name or 'shower' in name or 'dr06' in name or '09' in name:
                    cat = 'wall_right'
                elif 'north' in name or 'dr12' in name or 'tub' in name or 'w05' in name or 'w06' in name or '08' in name or 'screen' in name:
                    cat = 'wall_mid'
                else:
                    bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                    xs = [b.x for b in bb]; ys = [b.y for b in bb]; zs = [b.z for b in bb]
                    avg_x = sum(xs)/len(xs); avg_y = sum(ys)/len(ys); avg_z = sum(zs)/len(zs)
                    if avg_z < 0.02:
                        cat = 'floor'
                    elif avg_z > 2.80:
                        cat = 'ceiling'
                    elif avg_x < 1.0:
                        cat = 'wall_left'
                    elif avg_x > 1.8:
                        cat = 'wall_right'
                    else:
                        cat = 'wall_mid'

            obj.data.materials.clear()
            obj.data.materials.append(mats[cat])

        out_path = f"/tmp/mask_{cam_name}_fixed.png"
        scene.render.filepath = out_path
        print(f"Rendering mask for {cam_name} to {out_path}...")
        bpy.ops.render.render(write_still=True)
        print(f"Rendered {out_path}")

if __name__ == '__main__':
    render_masks()
