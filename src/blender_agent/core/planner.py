import json

from blender_agent.core.llm import LLMClient
from blender_agent.core.types import Plan, Step, ChatMessage

SYSTEM = ("你是 3D 制作规划器。把用户的 3D 任务拆成有序、可独立执行的小步骤。"
          "每一步是一个 Agent 能用 Blender MCP 工具完成的明确目标。"
          "只输出 JSON：{\"steps\":[{\"goal\":\"...\"}]}。")


class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def plan(self, goal: str, scene: str = "") -> Plan:
        user = f"当前场景：{scene}\n任务：{goal}\n请拆解步骤。"
        msg = self.llm.chat([ChatMessage(role="system", content=SYSTEM),
                             ChatMessage(role="user", content=user)])
        try:
            data = json.loads(msg.content)
            steps = [Step(index=i, goal=g["goal"]) for i, g in enumerate(data["steps"])]
        except Exception:  # noqa: LLM 没给干净 JSON 时退化为单步
            steps = [Step(index=0, goal=goal)]
        return Plan(goal=goal, steps=steps)
