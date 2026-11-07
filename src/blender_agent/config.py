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
    model: str = "nvidia/nemotron-3.5-super-vl:free"
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


def _load_env_file(path: str = ".env") -> None:
    """轻量解析 .env（KEY=VALUE，支持 # 注释），不覆盖已存在的环境变量。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if v[:1] in ('"', "'"):  # 引号包裹：保留原样（含 #）
                v = v.strip('"').strip("'")
            else:  # 未包裹：去掉行内注释
                v = v.split("#", 1)[0].strip()
            if k and k not in os.environ:
                os.environ[k] = v


def load_config() -> AgentConfig:
    _load_env_file()
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
