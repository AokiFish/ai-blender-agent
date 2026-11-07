import pytest
from blender_agent.core.tool_provider import StubToolProvider, discovered_tools_to_openai
from blender_agent.core.types import AgentTool


def test_stub_lists_and_calls():
    stub = StubToolProvider({
        "create_cube": lambda args: f"created cube size={args.get('size')}",
    })
    tools = stub.sync_list_tools()
    assert any(t.name == "create_cube" for t in tools)
    res = stub.sync_call_tool("create_cube", {"size": 2})
    assert res.ok and "size=2" in res.content


def test_to_openai_schema():
    t = AgentTool(name="x", description="d",
                  input_schema={"type": "object", "properties": {"a": {"type": "number"}}})
    oai = discovered_tools_to_openai([t])
    assert oai[0]["type"] == "function"
    assert oai[0]["function"]["name"] == "x"
