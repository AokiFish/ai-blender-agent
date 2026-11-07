import os

import pytest

from blender_agent.config import BlenderMCPConfig, Transport
from blender_agent.core.mcp_adapter import McpToolProvider


@pytest.mark.skipif(os.getenv("BLENDER_AGENT_LIVE") != "1",
                    reason="需要真实 Blender + MCP server")
@pytest.mark.asyncio
async def test_live_list_and_call():
    cfg = BlenderMCPConfig(transport=Transport.STDIO)
    p = McpToolProvider(cfg)
    tools = await p.list_tools()
    assert any(t.name for t in tools)
