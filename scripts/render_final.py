"""无头渲染：打开 result.blend 用相机渲染一张正视图。"""
import bpy

scn = bpy.context.scene
scn.render.engine = 'BLENDER_EEVEE'
scn.render.resolution_x = 800
scn.render.resolution_y = 800
scn.view_settings.view_transform = "Standard"
scn.render.filepath = "D:/Mydata/WorkBuddy/AI-blender-agent/workspace/result_final.png"
bpy.ops.render.render(write_still=True)
print("RENDER_DONE")
