from abc import ABC, abstractmethod

from blender_agent.core.types import AgentTool, ToolResult


class ToolProvider(ABC):
    @abstractmethod
    async def list_tools(self) -> list[AgentTool]: ...

    @abstractmethod
    async def call_tool(self, name: str, args: dict) -> ToolResult: ...


class StubToolProvider(ToolProvider):
    """测试/演示用：纯内存工具，无需 Blender。"""

    def __init__(self, handlers: dict[str, callable]):
        self._tools = [
            AgentTool(name=n, description=f"stub:{n}",
                      input_schema={"type": "object", "properties": {}})
            for n in handlers
        ]
        self._handlers = handlers

    def sync_list_tools(self) -> list[AgentTool]:
        return self._tools

    def sync_call_tool(self, name: str, args: dict) -> ToolResult:
        try:
            out = self._handlers[name](args)
            return ToolResult(ok=True, content=str(out))
        except Exception as e:  # noqa: 测试桩把异常转成失败结果
            return ToolResult(ok=False, error=str(e))

    async def list_tools(self):
        return self.sync_list_tools()

    async def call_tool(self, name, args):
        return self.sync_call_tool(name, args)


def discovered_tools_to_openai(tools: list[AgentTool]) -> list[dict]:
    return [{
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
        },
    } for t in tools]
