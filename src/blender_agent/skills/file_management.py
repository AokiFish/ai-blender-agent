from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class FileManagement(Skill):
    name = "file_management"

    def __init__(self, provider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        g = goal.lower()
        return any(k in g for k in ["保存", "导出", "save", "export", ".blend", "fbx", "glb"])

    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        ctx = ctx or {}
        workspace = ctx.get("workspace", ".")
        base = ctx.get("base_name", "result")
        steps = [Step(index=0,
                     goal=f"用 execute_blender_code 把工程保存到 {workspace}/{base}.blend")]
        g = goal.lower()
        if "fbx" in g or "导出" in goal:
            steps.append(Step(index=len(steps),
                             goal=f"用 execute_blender_code 导出 FBX 到 {workspace}/{base}.fbx"))
        if "glb" in g or "导出" in goal:
            steps.append(Step(index=len(steps),
                             goal=f"用 execute_blender_code 导出 GLB 到 {workspace}/{base}.glb"))
        return steps

    @staticmethod
    def expected_paths(goal: str, workspace: str = ".", base: str = "result") -> list[str]:
        paths = [f"{workspace}/{base}.blend"]
        g = goal.lower()
        if "fbx" in g or "导出" in goal:
            paths.append(f"{workspace}/{base}.fbx")
        if "glb" in g or "导出" in goal:
            paths.append(f"{workspace}/{base}.glb")
        return paths
