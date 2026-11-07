from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class NLModeling(Skill):
    name = "nl_modeling"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["建", "做", "创建", "模型", "生成"])

    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0, goal=f"根据描述创建基础几何：{goal}"),
            Step(index=1, goal="调整尺寸/位置/旋转使其符合描述"),
            Step(index=2, goal="为模型赋予合适的材质与颜色"),
            Step(index=3, goal="渲染视图自检并修复明显问题"),
        ]
