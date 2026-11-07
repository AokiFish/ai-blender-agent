from blender_agent.skills.animation import Animation
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step


def test_animation_builds_steps_for_walk():
    stub = StubToolProvider({})
    steps = Animation(stub).build_steps("基础走路动画")
    assert any("走路" in s.goal for s in steps)
    assert any("关键帧" in s.goal or "渲染" in s.goal for s in steps)
