from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class SceneUnderstanding(Skill):
    name = "scene_understanding"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["场景", "看", "分析", "有什么"])

    def report(self) -> str:
        res = self.provider.sync_call_tool("get_scene_info", {})
        return res.content

    def build_steps(self, goal: str, ctx: dict) -> list[Step]:
        return [Step(index=0, goal=f"读取并汇报当前场景：{goal}")]
