"""检查 glb 的 UV / 顶点色 / 材质。"""
import bpy

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath="D:/Mydata/WorkBuddy/AI-blender-agent/workspace/cat_local3d.glb")
for o in bpy.context.scene.objects:
    if o.type != "MESH":
        continue
    me = o.data
    print("MESH", o.name, "| faces", len(me.polygons),
          "| uvs", [l.name for l in me.uv_layers],
          "| colors", [l.name for l in me.color_attributes],
          "| mats", [m.name for m in me.materials])
