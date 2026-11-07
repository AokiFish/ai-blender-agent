"""纯灰渲染，用来判断侧面的方块台阶是几何/法线问题还是顶点色问题。"""
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = argv[0], argv[1]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=GLB)
obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
me = obj.data
n = len(me.vertices)
attr = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
attr.data.foreach_set("color", np.full((n, 4), 0.55, dtype=np.float32).ravel())
me.color_attributes.active_color = attr

mat = bpy.data.materials.new("G")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.6
bsdf.inputs["Base Color"].default_value = (0.55, 0.55, 0.58, 1.0)
me.materials.clear()
me.materials.append(mat)

co = np.empty(n * 3); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
mn, mx = co.min(axis=0), co.max(axis=0)
center = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
size = float((mx - mn).max())

scn = bpy.context.scene
scn.render.engine = "BLENDER_EEVEE"
scn.render.resolution_x = scn.render.resolution_y = 800
scn.view_settings.view_transform = "Standard"
scn.world = bpy.data.worlds.new("W")
scn.world.use_nodes = True
scn.world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.06, 0.09, 1)
for i, pos in enumerate([(2.5, -2.5, 3.0), (-3.0, -1.5, 1.5), (0.0, 3.0, 2.0)]):
    ld = bpy.data.lights.new(f"L{i}", type="AREA")
    ld.energy, ld.size, ld.use_shadow = [900, 400, 350][i], 4, False
    lo = bpy.data.objects.new(f"L{i}", ld)
    lo.location = Vector(pos) * size / 2
    scn.collection.objects.link(lo)

cam_data = bpy.data.cameras.new("C"); cam_data.lens = 60
cam = bpy.data.objects.new("C", cam_data)
scn.collection.objects.link(cam); scn.camera = cam
cam.location = center + Vector((size * 2.4, 0, 0.05 * size))
cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
scn.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("GRAY_OK", OUT)
