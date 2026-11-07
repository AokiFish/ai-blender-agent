from blender_agent.core.llm import FakeLLM, LLMClient
from blender_agent.core.types import ChatMessage


def test_fake_llm_returns_preset_tool_call():
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", tool_calls=[{
            "id": "c1", "type": "function",
            "function": {"name": "create_primitive", "arguments": '{"type":"sphere"}'}}])
    ])
    msg = fake.chat([ChatMessage(role="user", content="做个球")], tools=[])
    assert msg.tool_calls[0]["function"]["name"] == "create_primitive"


def test_fake_llm_returns_text_when_exhausted():
    fake = FakeLLM(responses=[ChatMessage(role="assistant", content="完成")])
    msg = fake.chat([], tools=[])
    assert msg.content == "完成"
