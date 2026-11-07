from blender_agent.skills.talking_head import TalkingHead
from blender_agent.core.tool_provider import StubToolProvider


def test_accepts_image_or_talking_goal():
    stub = StubToolProvider({})
    assert TalkingHead(stub).accept("上传猫咪图片，做口播角色") is True
    assert TalkingHead(stub).accept("做一个红色立方体") is False


def test_builds_full_talking_head_pipeline():
    stub = StubToolProvider({})
    steps = TalkingHead(stub).build_steps("参考猫咪图片做口播角色", has_image=True)
    goals = " ".join(s.goal for s in steps)
    for kw in ["建模", "材质", "骨骼", "绑定", "嘴", "眼", "贴图", "自检"]:
        assert kw in goals, kw
