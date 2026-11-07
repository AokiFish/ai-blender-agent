from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class Animation(Skill):
    name = "animation"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["动画", "走路", "跑步", "表情", "动作", "animat", "walk", "run"])

    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0, goal=f"为角色设置动画：{goal}"),
            Step(index=1, goal="在关键帧上编排肢体/骨骼运动"),
            Step(index=2, goal="调整时序与循环使其自然"),
            Step(index=3, goal="渲染动画序列帧自检并修复穿模/滑步"),
        ]
