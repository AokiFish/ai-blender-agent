"""glb -> 三视图渲染（无头）。用法: blender -b -P render_glb.py -- <input.glb> <out_prefix>"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = argv[0] if argv else "D:/Mydata/WorkBuddy/AI-blender-agent/workspace/cat_local3d.glb"
PREFIX = argv[1] if len(argv) > 1 else "D:/Mydata/WorkBuddy/AI-blender-agent/workspace/cat_local3d"

# 清场
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=GLB)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("NO_MESH")
    sys.exit(1)

# 全场景包围盒
mn = Vector((1e9, 1e9, 1e9))
mx = Vector((-1e9, -1e9, -1e9))
for o in meshes:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        for i in range(3):
            mn[i] = min(mn[i], w[i])
            mx[i] = max(mx[i], w[i])
center = (mn + mx) / 2
size = max((mx - mn)[i] for i in range(3))
print(f"BOUNDS size={size:.3f} center={tuple(round(v,3) for v in center)}")

scn = bpy.context.scene
scn.render.engine = "BLENDER_EEVEE"
scn.render.resolution_x = 900
scn.render.resolution_y = 900
scn.render.film_transparent = False
scn.view_settings.view_transform = "Standard"
scn.world = bpy.data.worlds.new("W")
scn.world.use_nodes = True
scn.world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.09, 1)
scn.world.node_tree.nodes["Background"].inputs[1].default_value = 0.6

# 三盏灯
for i, (pos, energy) in enumerate([
    ((2.5, -2.5, 3.0), 900), ((-3.0, -1.5, 1.5), 400), ((0.0, 3.5, 2.0), 300),
]):
    ld = bpy.data.lights.new(f"L{i}", type="AREA")
    ld.energy = energy
    ld.size = 4
    lo = bpy.data.objects.new(f"L{i}", ld)
    lo.location = Vector(pos) * size / 2
    scn.collection.objects.link(lo)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 60
cam = bpy.data.objects.new("Cam", cam_data)
scn.collection.objects.link(cam)
scn.camera = cam

dist = size * 1.9
views = {
    "front": (0, -dist, 0.06 * size),
    "side": (dist, 0, 0.06 * size),
    "q45": (dist * 0.72, -dist * 0.72, 0.12 * size),
}
for name, offset in views.items():
    cam.location = center + Vector(offset)
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scn.render.filepath = f"{PREFIX}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {name}")

print("RENDER_ALL_OK")
