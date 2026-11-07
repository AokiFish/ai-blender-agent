import base64

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from blender_agent.config import BlenderMCPConfig, Transport
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import AgentTool, ToolResult


class McpToolProvider(ToolProvider):
    def __init__(self, cfg: BlenderMCPConfig):
        self.cfg = cfg
        self._session: ClientSession | None = None
        self._ctx = None

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

    async def list_tools(self) -> list[AgentTool]:
        await self._connect()
        tools = await self._session.list_tools()
        out = []
        for t in tools.tools:
            returns_img = any(k in t.name for k in ("render", "snapshot", "screenshot"))
            out.append(AgentTool(
                name=t.name,
                description=t.description or "",
                input_schema=t.inputSchema or {"type": "object", "properties": {}},
                returns_image=returns_img,
            ))
        return out

    async def call_tool(self, name: str, args: dict) -> ToolResult:
        if not self._session:
            await self._connect()
        res = await self._session.call_tool(name, arguments=args)
        content, images = [], []
        for block in res.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                content.append(block.text)
            elif btype == "image":
                images.append(base64.b64decode(block.data))
        return ToolResult(
            ok=not res.isError,
            content="\n".join(content),
            images=images,
            error=None if not res.isError else "\n".join(content),
        )
