"""真实 Blender 验证：形态键必须落在「上半部区域里面数最多」的网格上。

构造三个网格：Body（低处、面多）、Head（高处、面多）、Ear_L（高处、面少）。
预期 target=Head，且 Blink/MouthOpen 挂在 Head 上。
"""
import sys

sys.path.insert(0, r"D:/Mydata/WorkBuddy/AI-blender-agent/src")

import bpy
from blender_agent.builders.rig import rig_script

# 清场
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# Body：低处，多面
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0.5))
body = bpy.context.object
body.name = "Body"
bpy.ops.object.mode_set(mode='EDIT')
for _ in range(3):
    bpy.ops.mesh.subdivide()
bpy.ops.object.mode_set(mode='OBJECT')

# Head：高处（中心 z 约 1.8），多面
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, location=(0, -0.2, 1.8), segments=32, ring_count=24)
head = bpy.context.object
head.name = "Head"

# Ear_L：高处但面少
bpy.ops.mesh.primitive_cone_add(radius1=0.3, depth=0.6, vertices=8, location=(0.4, -0.2, 2.6))
ear = bpy.context.object
ear.name = "Ear_L"

bpy.ops.object.select_all(action='DESELECT')

code = rig_script("")
print("=" * 60)
exec(code, {"__name__": "__rig__"})
print("=" * 60)
print("EXPECT target=Head, keys contains Blink/MouthOpen")
