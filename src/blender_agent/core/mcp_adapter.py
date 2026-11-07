import asyncio
import base64

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from blender_agent.config import BlenderMCPConfig, Transport
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import AgentTool, ToolResult


class McpToolProvider(ToolProvider):
    """通过 MCP 连接 Blender（默认 ahujasid/mcp-for-blender）。

    mcp-for-blender 真实只暴露 9 个工具，建模/保存/导出全部靠
    ``execute_blender_code`` 跑 bpy 代码完成，因此本类只负责连接与转发，
    工具选择交给 LLM。

    关键点：连接只建立一次（常驻事件循环 + 会话），sync 与 async API
    都提交到同一个 loop，避免“跨事件循环使用 session”的报错。
    """

    def __init__(self, cfg: BlenderMCPConfig):
        self.cfg = cfg
        self._loop = None
        self._session = None
        self._ctx = None

    def _ensure_connected(self):
        if self._session is not None:
            return
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._connect())
        except Exception as e:  # noqa: 连不上时给出可操作的提示
            self._loop.close()
            self._loop = None
            raise RuntimeError(
                "无法连接 Blender MCP：请确认 ① Blender 已打开 ② 已启用 "
                "“Interface: MCP for Blender” 插件 ③ 在 3D 视图 N 面板启动了 MCP Server。"
                f" 原始错误：{e}"
            ) from e

    async def _connect(self):
        if self.cfg.transport == Transport.HTTP:
            self._ctx = streamable_http_client(self.cfg.http_url)
        else:
            params = StdioServerParameters(command=self.cfg.command, args=self.cfg.args)
            self._ctx = stdio_client(params)
        read, write, *_ = await self._ctx.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    def _run(self, coro_factory):
        """先确保连接，再在常驻事件循环上执行协程工厂（先连后建协程）。"""
        self._ensure_connected()
        return self._loop.run_until_complete(coro_factory())

    # ---- sync API（Agent / Observer / Skills 使用）----
    def sync_list_tools(self) -> list[AgentTool]:
        raw = self._run(lambda: self._session.list_tools())
        return self._to_agent_tools(raw.tools)

    def sync_call_tool(self, name: str, args: dict) -> ToolResult:
        res = self._run(lambda: self._session.call_tool(name, arguments=args))
        return self._to_tool_result(res)

    # ---- async API（兼容）----
    async def list_tools(self) -> list[AgentTool]:
        self._ensure_connected()
        raw = await self._session.list_tools()
        return self._to_agent_tools(raw.tools)

    async def call_tool(self, name: str, args: dict) -> ToolResult:
        self._ensure_connected()
        res = await self._session.call_tool(name, arguments=args)
        return self._to_tool_result(res)

    @staticmethod
    def _to_agent_tools(tools):
        out = []
        for t in tools:
            name = t.name
            # 真实截图/渲染工具是 `look`；也兼容 render/screenshot 等命名
            returns_img = any(k in name.lower() for k in
                             ("render", "snapshot", "screenshot", "look",
                              "viewport", "view", "image"))
            out.append(AgentTool(
                name=name,
                description=t.description or "",
                input_schema=t.input_schema or {"type": "object", "properties": {}},
                returns_image=returns_img,
            ))
        return out

    @staticmethod
    def _to_tool_result(res):
        content, images = [], []
        for block in res.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                content.append(block.text)
            elif btype == "image":
                images.append(base64.b64decode(block.data))
        return ToolResult(
            ok=not res.is_error,
            content="\n".join(content),
            images=images,
            error=None if not res.is_error else "\n".join(content),
        )
