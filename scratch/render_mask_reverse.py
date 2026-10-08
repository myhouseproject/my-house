import bpy

bpy.ops.wm.open_mainfile(filepath="/tmp/test_baseline/bathroom-entrance-preview.blend")
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

# For reverse camera: looking north towards entrance
# Left is West wall (Right wall in entrance view)
# Right is East wall (Left wall in entrance view)
# Middle is North wall
for obj in scene.objects:
    if obj.type != 'MESH':
        continue
    name = obj.name.lower()
    
    category = None
    if 'floor' in name:
        category = 'floor'
    elif 'ceiling' in name:
        category = 'ceiling'
    elif 'north' in name:
        category = 'wall_mid'
    elif 'west' in name:
        # In reverse view, looking towards North: West (X=2.6) is on the LEFT
        category = 'wall_left'
    elif 'east' in name:
        # In reverse view, looking towards North: East (X=0) is on the RIGHT
        category = 'wall_right'
    elif 'south' in name:
        category = 'wall_mid'
    else:
        from mathutils import Vector
        bb = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        xs = [b.x for b in bb]; ys = [b.y for b in bb]; zs = [b.z for b in bb]
        avg_x = sum(xs)/len(xs)
        avg_y = sum(ys)/len(ys)
        avg_z = sum(zs)/len(zs)
        
        if avg_z < 0.5:
            category = 'floor'
        elif avg_z > 2.4:
            category = 'ceiling'
        elif avg_y < 1.0:
            category = 'wall_mid'
        elif avg_x > 1.8:
            category = 'wall_left'
        elif avg_x < 0.8:
            category = 'wall_right'
        else:
            category = 'wall_mid'
            
    obj.data.materials.clear()
    obj.data.materials.append(mats[category])

scene.world.use_nodes = True
bg = scene.world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Strength'].default_value = 0.0

for obj in scene.objects:
    if obj.type == 'LIGHT':
        obj.data.energy = 0.0

# Set active camera to reverse
cam_rev = scene.objects.get('Camera_reverse')
if cam_rev:
    scene.camera = cam_rev

scene.cycles.samples = 1
scene.view_settings.view_transform = 'Standard'
scene.view_settings.exposure = 0.0
scene.render.resolution_x = 2000
scene.render.resolution_y = 1600
scene.render.filepath = '/tmp/mask_reverse_test.png'

bpy.ops.render.render(write_still=True)
print("Saved /tmp/mask_reverse_test.png successfully!")
