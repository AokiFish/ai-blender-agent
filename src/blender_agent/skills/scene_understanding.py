from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class SceneUnderstanding(Skill):
    name = "scene_understanding"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        # 动作词优先让给建模/角色/动画类 skill，避免"在场景中创建X"被截胡
        if any(k in goal for k in ["创建", "建模", "做", "制作", "生成",
                                   "添加", "动画", "绑定", "导出", "保存"]):
            return False
        return any(k in goal for k in ["场景", "看", "分析", "有什么"])

    def report(self) -> str:
        res = self.provider.sync_call_tool("get_scene_info", {})
        return res.content

    def build_steps(self, goal: str, ctx: dict) -> list[Step]:
        return [Step(index=0, goal=f"读取并汇报当前场景：{goal}")]
