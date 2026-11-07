import asyncio
import json

from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider, discovered_tools_to_openai
from blender_agent.core.types import AgentTool, ChatMessage, Step, ToolResult

EXEC_SYS = ("你是 Blender 操作执行者。根据步骤目标，调用可用工具完成它；"
            "每轮最多调用一个工具，拿到结果后继续，直到目标达成后只回复文字总结，不再调用工具。")


class Executor:
    def __init__(self, llm: LLMClient, provider: ToolProvider, inner_max: int = 8):
        self.llm, self.provider, self.inner_max = llm, provider, inner_max

    def run_step(self, step: Step, tools: list[AgentTool], history: list[ChatMessage]) -> ToolResult:
        msgs = [ChatMessage(role="system", content=EXEC_SYS),
                ChatMessage(role="user", content=f"步骤目标：{step.goal}")] + list(history)
        oai_tools = discovered_tools_to_openai(tools)
        collected = []
        for _ in range(self.inner_max):
            reply = self.llm.chat(msgs, tools=oai_tools)
            if not reply.tool_calls:
                collected.append(reply.content)
                break
            for tc in reply.tool_calls:
                fn = tc["function"]
                args = _safe_json(fn.get("arguments", "{}"))
                msgs.append(ChatMessage(role="assistant", content=reply.content, tool_calls=[tc]))
                if hasattr(self.provider, "sync_call_tool"):
                    result = self.provider.sync_call_tool(fn["name"], args)
                else:
                    result = _run(self.provider.call_tool(fn["name"], args))
                msgs.append(ChatMessage(role="tool", content=result.content,
                                        tool_call_id=tc["id"], images=result.images))
                collected.append(result.content)
        return ToolResult(ok=True, content="\n".join(collected))


def _safe_json(s: str) -> dict:
    try:
        return json.loads(s or "{}")
    except Exception:
        return {}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
