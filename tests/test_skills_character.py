from blender_agent.skills.character import Character
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step


def test_character_has_full_pipeline_steps():
    stub = StubToolProvider({})
    steps = Character(stub).build_steps("给 Mimi 做完整角色")
    goals = " ".join(s.goal for s in steps)
    for kw in ["建模", "材质", "骨骼", "绑定", "表情", "控制器"]:
        assert kw in goals, kw
