from blender_agent.core.executor import Executor
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage, Step


def test_executor_runs_tool_then_finishes():
    stub = StubToolProvider({"create_primitive": lambda a: f"ok {a}"})
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", tool_calls=[{"id": "c1", "type": "function",
            "function": {"name": "create_primitive", "arguments": '{"type":"cube"}'}}]),
        ChatMessage(role="assistant", content="完成"),
    ])
    ex = Executor(fake, stub)
    tools = stub.sync_list_tools()
    res = ex.run_step(Step(index=0, goal="建立方体"), tools, [])
    assert res.ok and "ok" in res.content
