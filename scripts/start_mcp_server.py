"""Blender 启动脚本：启用 blender_mcp 插件并自动开 MCP 服务（9876）。

用法：blender.exe -P scripts/start_mcp_server.py
"""
import addon_utils
import bpy

addon_utils.enable("blender_mcp", default_set=True, persistent=True)

scene = bpy.context.scene
if hasattr(scene, "blendermcp_port"):
    scene.blendermcp_port = 9876

try:
    bpy.ops.blendermcp.start_server()
    print("MCP_SERVER_STARTED port=9876")
except Exception as e:  # noqa
    print("MCP_SERVER_START_FAILED:", e)

if hasattr(scene, "blendermcp_auto_start_server"):
    scene.blendermcp_auto_start_server = True
