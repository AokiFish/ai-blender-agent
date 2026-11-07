import asyncio
import json

from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider, discovered_tools_to_openai
from blender_agent.core.types import AgentTool, ChatMessage, Step, ToolResult

EXEC_SYS = (
    "你是资深 Blender 角色技术美术（TA），通过 execute_blender_code 编写 bpy 代码完成建模任务。\n"
    "硬性质量要求（违反任何一条都算未完成）：\n"
    "1. 几何必须具体：不允许只放几个原始方块/球体交差。角色必须有可辨识的五官——"
    "眼睛（独立眼球网格，含瞳孔/虹膜面）、鼻子、嘴（含口腔内壁几何）、耳朵等，"
    "用球体/缩放/布尔/细分+变形组合成形，细节程度要能一眼认出是什么角色。\n"
    "2. 材质必须逐面分配：用 bmesh 按空间位置把面分给对应材质槽（设置 polygon.material_index）。"
    "完成后必须统计并打印每个材质槽的面数，任何槽为 0 面都算失败，必须修复。\n"
    "3. 建完每个主要部件（头部/眼睛/嘴/耳/身体）立即调用 look 工具查看效果，"
    "不满意当场修改，不要把问题累积到最后。\n"
    "4. 代码分多次小段执行（每次只做一个部件），避免超长代码一次执行失败。\n"
    "5. 参考图（如果上下文里有）是唯一外观标准：配色、比例、特征（项圈/铃铛/花纹等）都必须体现。\n"
    "每轮最多调用一个工具，拿到结果后继续，直到目标真正达成后才用文字总结，不再调用工具。")


class Executor:
    def __init__(self, llm: LLMClient, provider: ToolProvider, inner_max: int = 24):
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
