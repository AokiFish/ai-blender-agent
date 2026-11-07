from enum import Enum

from pydantic import BaseModel, Field
import os


class Transport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


class ModelProvider(BaseModel):
    name: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = "google/gemma-4-26b-it:free"
    vision: bool = True
    max_tokens: int = 4096
    temperature: float = 0.2


class BlenderMCPConfig(BaseModel):
    transport: Transport = Transport.STDIO
    command: str = "uvx"
    args: list[str] = Field(default_factory=lambda: ["mcp-for-blender"])
    http_url: str = "http://127.0.0.1:9765/mcp"
    timeout: float = 120.0


class AgentConfig(BaseModel):
    provider: ModelProvider = Field(default_factory=ModelProvider)
    blender: BlenderMCPConfig = Field(default_factory=BlenderMCPConfig)
    workspace: str = "./workspace"
    max_steps: int = 40


def load_config() -> AgentConfig:
    p = ModelProvider(
        base_url=os.getenv("BLENDER_AGENT_BASE_URL", ModelProvider().base_url),
        api_key=os.getenv("BLENDER_AGENT_API_KEY", ""),
        model=os.getenv("BLENDER_AGENT_MODEL", ModelProvider().model),
    )
    b = BlenderMCPConfig(
        transport=Transport(os.getenv("BLENDER_AGENT_MCP_TRANSPORT", "stdio")),
        command=os.getenv("BLENDER_AGENT_MCP_COMMAND", "uvx"),
        args=os.getenv("BLENDER_AGENT_MCP_ARGS", "mcp-for-blender").split(),
        http_url=os.getenv("BLENDER_AGENT_MCP_HTTP_URL", BlenderMCPConfig().http_url),
    )
    return AgentConfig(
        provider=p,
        blender=b,
        workspace=os.getenv("BLENDER_AGENT_WORKSPACE", "./workspace"),
        max_steps=int(os.getenv("BLENDER_AGENT_MAX_STEPS", "40")),
    )
