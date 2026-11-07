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
        if ctx and ctx.get("has_image"):
            has_image = True
        ref = "参考上传图片" if has_image else "按描述"
        return [
            Step(index=0, goal=(
                f"{ref}建模：清理场景（删除旧角色与 .001 重复对象）并搭建角色基础形体："
                "头部大球+吻部小球+身体，比例必须对照参考图；"
                "完成后立即用 look 检查整体比例是否像参考图")),
            Step(index=1, goal=(
                "创建五官几何【硬性要求，缺一项都必须回去补】："
                "两只独立眼球网格（球体，含瞳孔/虹膜材质面）+ 鼻子（小球/三角）+ "
                "嘴部（上下唇几何，含口腔内壁，供口型 shape key 变形）+ "
                "耳朵（参考图为尖耳则做锥形耳）+ 胡须可选。"
                "每建完一个部件立即用 look 验证位置和大小")),
            Step(index=2, goal=(
                "逐面分配材质【硬性要求】：用 bmesh 按空间位置把面分给对应材质槽"
                "（皮肤毛色/眼睛白/瞳孔/鼻子/嘴内/项圈/铃铛），设置 polygon.material_index。"
                "完成后用代码统计并打印每个材质槽的面数，任何槽为 0 面必须当场修复；"
                "再 look 确认颜色分区正确")),
            Step(index=3, goal=(
                "创建骨架并绑定：Cat_Armature 含 Head/LeftEye_Ball/RightEye_Ball/"
                "Mouth/四肢/尾巴骨骼，自动权重后对眼部/嘴部区域手工修正权重，"
                "确保眼球只跟 Eye 骨、嘴周只跟 Mouth 骨")),
            Step(index=4, goal=(
                "嘴部控制器【交付物，导出后必须可用】：MouthOpen/MouthCorner/Smile "
                "shape keys + Mouth 骨驱动。验证方式：代码把 MouthOpen 值设为 1 → "
                "look 截图确认嘴明显张开 → 归零。验证不通过必须修")),
            Step(index=5, goal=(
                "眼部控制器【交付物，导出后必须可用】：眼球追踪骨骼（Track To 约束或 "
                "Eye_Target 骨）+ Blink 眨眼 shape key。验证方式：Blink 值设 1 → "
                "look 确认眼皮闭合 → 归零；眼球骨骼旋转 → look 确认眼球转向")),
            Step(index=6, goal=(
                "UV 展开 + 模块化贴图槽：Smart UV Project，每个可换贴图部位"
                "（脸/眼/嘴内/项圈/铃铛）独立材质槽与 UV 通道，便于后期单独替换贴图")),
            Step(index=7, goal=(
                "整体自检【必须与参考图对照】：look 正面渲染，逐项核对参考图的"
                "轮廓/五官/配色/特征（项圈铃铛等），列出差距并当场修复，"
                "重复直到渲染图能一眼认出是参考图里的角色")),
        ]
