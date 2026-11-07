from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import ChatMessage, ToolResult

DETERMINISTIC_SCRIPT = """
import bpy
me = [o.data for o in bpy.data.objects if o.type == 'MESH']
nm = sum(len(m.validate()) for m in me)
za = sum(1 for m in me for f in m.polygons if f.area < 1e-6)
mt = sum(1 for o in bpy.data.objects if o.type == 'MESH' and not o.material_slots)
print(f"non_manifold_edges:{nm}")
print(f"zero_area_faces:{za}")
print(f"meshes_missing_material:{mt}")
"""


class Observer:
    def __init__(self, provider: ToolProvider, vlm: LLMClient | None = None):
        self.provider, self.vlm = provider, vlm

    def check(self, goal: str, step_result: ToolResult | None) -> dict:
        issues = []
        res = self.provider.sync_call_tool("execute_python", {"code": DETERMINISTIC_SCRIPT})
        for line in res.content.splitlines():
            if line.startswith("non_manifold_edges:") and int(line.split(":")[1]) > 0:
                issues.append(f"存在 {line.split(':')[1]} 条非流形边")
            if line.startswith("zero_area_faces:") and int(line.split(":")[1]) > 0:
                issues.append(f"存在 {line.split(':')[1]} 个零面积面")
            if line.startswith("meshes_missing_material:") and int(line.split(":")[1]) > 0:
                issues.append(f"有 {line.split(':')[1]} 个网格缺材质")
        images = step_result.images if step_result else []
        if self.vlm and images:  # 可选：把截图交给视觉模型复核
            v = self.vlm.chat([ChatMessage(
                role="user",
                content=f"这张 3D 视图是否符合目标：{goal}？只列问题。")],
                tools=None)
            if v.content.strip():
                issues.append(f"VLM: {v.content.strip()}")
        return {"passed": len(issues) == 0, "issues": issues, "images": images}
