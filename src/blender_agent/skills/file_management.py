from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class FileManagement(Skill):
    name = "file_management"

    def __init__(self, provider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        g = goal.lower()
        return any(k in g for k in ["保存", "导出", "save", "export", ".blend", "fbx", "glb"])

    def build_steps(self, goal: str, ctx: dict) -> list[Step]:
        workspace = ctx.get("workspace", ".")
        base = ctx.get("base_name", "result")
        steps = [Step(index=0, goal=f"保存工程到 {workspace}/{base}.blend")]
        g = goal.lower()
        if "fbx" in g or "导出" in goal:
            steps.append(Step(index=len(steps), goal=f"导出 {base}.fbx"))
        if "glb" in g or "导出" in goal:
            steps.append(Step(index=len(steps), goal=f"导出 {base}.glb"))
        return steps

    def run(self, goal: str, workspace: str = ".", base_name: str = "result") -> dict:
        blend = f"{workspace}/{base_name}.blend"
        self.provider.sync_call_tool("save_blend", {"path": blend})
        deliverables = [blend]
        g = goal.lower()
        if "fbx" in g or "导出" in goal:
            fbx = f"{workspace}/{base_name}.fbx"
            self.provider.sync_call_tool("export_fbx", {"path": fbx})
            deliverables.append(fbx)
        if "glb" in g or "导出" in goal:
            glb = f"{workspace}/{base_name}.glb"
            self.provider.sync_call_tool("export_glb", {"path": glb})
            deliverables.append(glb)
        return {"deliverables": deliverables, "blend": blend}
