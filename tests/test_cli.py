from blender_agent.core.agent import Agent
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage


def test_agent_runs_full_loop():
    stub = StubToolProvider({
        "get_scene_info": lambda a: "Objects:[]",
        "create_primitive": lambda a: "ok",
        "set_material": lambda a: "ok",
        "save_blend": lambda a: "saved",
        "export_fbx": lambda a: "exp",
        "execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0",
    })
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", content='{"steps":[{"goal":"建模"},{"goal":"材质"}]}'),
        ChatMessage(role="assistant", tool_calls=[{"id": "c", "type": "function",
            "function": {"name": "create_primitive", "arguments": "{}"}}]),
        ChatMessage(role="assistant", content="建模完成"),
        ChatMessage(role="assistant", tool_calls=[{"id": "c", "type": "function",
            "function": {"name": "set_material", "arguments": "{}"}}]),
        ChatMessage(role="assistant", content="材质完成"),
    ])
    agent = Agent.from_parts(fake, stub, workspace="/tmp/w")
    out = agent.run("给 Mimi 做角色")
    assert out["passed"] is True
    assert len(out["steps_log"]) >= 2


def test_agent_runs_with_image():
    stub = StubToolProvider({
        "get_scene_info": lambda a: "Objects:[]",
        "create_primitive": lambda a: "ok",
        "save_blend": lambda a: "saved",
        "export_fbx": lambda a: "exp",
        "execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0",
    })
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", content='{"steps":[{"goal":"建模"}]}'),
        ChatMessage(role="assistant", tool_calls=[{"id": "c", "type": "function",
            "function": {"name": "create_primitive", "arguments": "{}"}}]),
        ChatMessage(role="assistant", content="完成"),
    ])
    agent = Agent.from_parts(fake, stub, workspace="/tmp/w")
    out = agent.run("参考猫咪图片做口播角色", image=b"\x89PNG")
    assert out["passed"] is True
