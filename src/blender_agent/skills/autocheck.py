from blender_agent.core.observer import Observer
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step, ToolResult


class AutoCheck(Skill):
    name = "autocheck"

    def __init__(self, observer: Observer):
        self.observer = observer

    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["检查", "校验", "自检", "问题", "质量", "修复"])

    def build_steps(self, goal: str, ctx: dict) -> list[Step]:
        return [Step(index=0, goal=f"自动检查场景模型：{goal}")]

    def run(self, goal: str, step_result: ToolResult | None = None) -> dict:
        rep = self.observer.check(goal, step_result)
        rep["fixes"] = self._suggest_fixes(rep["issues"])
        return rep

    @staticmethod
    def _suggest_fixes(issues: list[str]) -> list[str]:
        fixes: list[str] = []
        for issue in issues:
            if "非流形" in issue:
                fixes.append("合并重叠顶点（bpy.ops.mesh.remove_doubles）或重建受影响网格。")
            elif "零面积" in issue:
                fixes.append("删除零面积面，并重新计算法线（recalculate normals）。")
            elif "缺材质" in issue:
                fixes.append("为每个网格对象分配材质槽并指定材质。")
            elif issue.startswith("VLM:"):
                fixes.append(f"按视觉反馈调整：{issue[len('VLM:'):].strip()}")
        return fixes
