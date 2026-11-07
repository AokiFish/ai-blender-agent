from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentTool:
    name: str
    description: str
    input_schema: dict  # JSON Schema（parameters）
    returns_image: bool = False


@dataclass
class ToolResult:
    ok: bool
    content: str = ""
    images: list[bytes] = field(default_factory=list)
    error: str | None = None


@dataclass
class ChatMessage:
    role: str  # system|user|assistant|tool
    content: str = ""
    images: list[bytes] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)  # OpenAI 格式
    tool_call_id: str | None = None


@dataclass
class Step:
    index: int
    goal: str
    status: str = "pending"  # pending|done|failed
    notes: str = ""


@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)
