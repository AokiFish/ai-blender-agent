from blender_agent.skills.nl_modeling import NLModeling
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step


def test_nl_modeling_builds_steps():
    stub = StubToolProvider({})
    steps = NLModeling(stub).build_steps("做一个红色球体")
    assert any("创建" in s.goal for s in steps)
    assert any("材质" in s.goal for s in steps)
