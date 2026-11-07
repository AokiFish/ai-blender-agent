from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class Character(Skill):
    name = "character"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["角色", "人物", "卡通人", "avatar", "Character"])

    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0, goal=f"建模角色身体与头部基础网格：{goal}"),
            Step(index=1, goal="为皮肤/衣服/眼睛分配 PBR 材质"),
            Step(index=2, goal="创建骨架（armature）并放置骨骼"),
            Step(index=3, goal="将网格与骨架绑定（parent + weights）"),
            Step(index=4, goal="添加面部骨骼与表情控制器（shape keys / bone constraints）"),
            Step(index=5, goal="渲染正面/侧面自检并修复拓扑与权重问题"),
        ]
