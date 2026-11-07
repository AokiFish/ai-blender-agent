from blender_agent.core.planner import Planner
from blender_agent.core.llm import FakeLLM
from blender_agent.core.types import ChatMessage


def test_planner_parses_steps_from_llm():
    fake = FakeLLM(responses=[ChatMessage(role="assistant", content=
        '{"steps":[{"goal":"建模身体"},{"goal":"做材质"},{"goal":"绑骨骼"}]}')])
    p = Planner(fake)
    plan = p.plan("给 Mimi 做角色", scene="空场景")
    assert [s.goal for s in plan.steps] == ["建模身体", "做材质", "绑骨骼"]
