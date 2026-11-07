from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step


class TalkingHead(Skill):
    name = "talking_head"

    def __init__(self, provider: ToolProvider):
        self.provider = provider

    def accept(self, goal: str) -> bool:
        explicit = any(k in goal for k in
            ["口播", "形象", "头像", "talking", "reference",
             "猫", "cat", "人脸", "照片", "图片", "图"])
        characterish = any(k in goal for k in ["角色", "人物"])
        return explicit and characterish

    def build_steps(self, goal: str, ctx: dict | None = None,
                    has_image: bool = False) -> list[Step]:
        ref = "参考上传图片" if has_image else "按描述"
        return [
            Step(index=0, goal=f"{ref}建模并建立角色头部与身体基础网格：{goal}"),
            Step(index=1, goal="分配皮肤/毛发/眼睛 PBR 材质（模块化材质槽，便于后期换贴图）"),
            Step(index=2, goal="创建骨架并绑定（含头部骨骼）"),
            Step(index=3, goal="添加【独立嘴部控制器】：口型 shape key（张嘴/嘴角）+ 骨骼，导出后仍可控"),
            Step(index=4, goal="添加【独立眼部控制器】：眼球看向骨骼 + 眨眼 shape key"),
            Step(index=5, goal="独立 UV 展开并建可替换贴图材质槽（模块化，便于后期单独换贴图）"),
            Step(index=6, goal="渲染正面/口型/眼神视图自检并修复权重与拓扑问题"),
        ]
