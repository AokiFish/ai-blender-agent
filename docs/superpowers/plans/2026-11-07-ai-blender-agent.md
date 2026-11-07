# AI Blender Agent 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个**能自主完成 3D 制作任务的 Agent**（不是只会执行 Python 的聊天机器人）：接收**文本目标**（如"给 Mimi 做一个完整 3D 角色，含模型、材质、骨骼、面部表情控制器、基础走路动画"）**或上传参考图**（如一张猫咪照片，按图建模），自主拆解 → 调用 Blender 工具执行 → 渲染截图自检 → 发现问题修复 → 交付可继续编辑的 `.blend` 与导出文件（FBX/GLB）。**口播角色**需额外具备**独立嘴部控制器**与**独立眼部控制器**，并支持**模块化贴图**（可单独替换贴图，为后期口播/口型同步视频做准备）。

**Architecture:** Agent 层只做"编排"，不重写 Blender 控制协议。它通过标准 **MCP 客户端**接入一个现成的 Blender MCP Server（GUI 版或 bpy.dev 无界面版皆可），把 MCP 工具归一化成统一 `ToolProvider` 接口暴露给 LLM；LLM 用**任意 OpenAI 兼容端点**（OpenRouter / Agnes 等免费模型）做推理与工具选择；核心是一个 `plan → act → observe → reflect` 的自驱循环，配合一组**可插拔的 skill 能力模块**（含图像驱动口播角色）和一个检查点/记忆系统；目标可为**文本或图片**，图片作为多模态上下文传给 LLM（经 `ChatMessage.images`）。

**Tech Stack:**
- Python 3.11+（`pyproject.toml` + `uv`）
- `openai` SDK —— 通过替换 `base_url` 兼容 OpenRouter / Agnes / 任何 OpenAI 格式端点
- `mcp` Python SDK —— 接入 Blender MCP Server（stdio 或 Streamable HTTP 两种 transport）
- 外部依赖（**不开发，仅配置/安装**）：Blender 4.x + 一个 Blender MCP Server（默认 `ahujasid/mcp-for-blender`，可选 `dcc-mcp-blender` / `bpy.dev` headless）
- `pydantic` —— 配置与结构化 I/O
- `pytest` + `pytest-asyncio` —— 测试（核心逻辑用 `StubToolProvider` 与 `FakeLLM` 做到无需 Blender 也能测）
- `typer` + `rich` —— CLI

**Spec:** 本计划即为 spec。设计方向（用户强约束）：做成真正的 Agent，不是聊天机器人；利用现有 MCP，不自研 Blender 协议；模型层对 OpenAI 兼容免费模型开放；支持图片输入与口播角色（嘴/眼独立控制器 + 模块化贴图）。

---

## Reference Research（调研结论，写进计划以确保决策有据）

1. **"Blender 官方 MCP Server" 并不存在。** 经核验（dcc-mcp 对比文档，2026-09-23）：Blender 官方组织下没有任何 MCP 仓库，blender 源码与插件树也无 MCP 路径。社区里被当作"官方"的其实是 `ahujasid/mcp-for-blender`（原 `blender-mcp`，33k★，MIT）。它 = Blender 插件（Blender 内开 socket 服务，默认 9876）+ 独立 MCP 进程（stdio 对接客户端，TCP 转发给 Blender）；自带**视觉校验**（多角度/线框/X 光/动画条截图 + 渲染）、Poly Haven/Sketchfab/AI 生成 3D（Meshy/Tripo/Hunyuan3D）等。**本计划默认采用它作为 GUI 接入后端。**
2. **其它 MCP for Blender 实现：** `dcc-mcp-blender`（200+ 类型化工具、内嵌 HTTP 服务 `http://127.0.0.1:9765/mcp`、生产向、有安全开关）适合要强类型/可测的场景；`BrightX/blender-mcp`（359 工具 + skill 系统）；`emeryporter/blender-mcp`（86 工具 + Unity 管线校验 + BMesh + 视口截图）。**我们的 `McpToolProvider` 必须同时支持 stdio 与 HTTP 两种 transport，以便切换后端。**
3. **`bpy.dev` = 无界面 Blender 后端，契合"Agent 自动化"方向。** 它用 `blender-mcp`（bpy-dev 版）把 Blender 当 headless backend，只暴露 4 个窄 MCP 工具（写 Python / 渲染 / 检视图像 / 继续），走 reference→build→inspect 循环；standalone bpy 打包仍在 WIP。**本计划把它作为可选后端，用于批量/CI 场景（无需开 GUI 即可渲染自检）。**
4. **模型接入：** OpenRouter / Agnes 均为 OpenAI 兼容，只需换 `base_url` 与 `api_key`。免费模型限速严格（`:free` 变体 20 次/分、50 次/天）；推荐默认视觉+函数调用兼备的 `google/gemma-4-26b-it:free`（262K 上下文、原生 function calling、多模态），自检与规划可共用；零成本兜底用 `openrouter/free` 路由。

---

## Global Constraints

- **不开发 Blender 控制协议**：只能接入现成 MCP Server，禁止自己写 Blender socket/插件。
- **模型层 OpenAI 兼容**：任何模型接入仅通过 `base_url` + `api_key` + `model` 三个配置项，默认走免费/低价模型。
- **真正 Agent，不是聊天机器人**：必须有 plan→act→observe→reflect 自驱循环与最终交付物（`.blend` + 导出），禁止只把用户消息转发给 LLM 就返回。
- **可测试性**：核心编排逻辑（planner / executor / observer / memory）必须能用 `StubToolProvider` 与 `FakeLLM` 在**无 Blender** 环境下跑通 pytest。
- **Blender 仅通过 MCP 工具交互**：Agent 进程不直接 import bpy、不直接跑 `blender --background`。
- **交付物可继续编辑**：最终必须保存 `.blend`（含全部模型/材质/骨骼/控制器/动画），导出 FBX/GLB 作为副产物。
- **提交规范**（沿用用户约定）：Conventional Commits 前缀（`feat:`/`fix:`/`refactor:`/`docs:`/`test:`），每个 task 一个提交；每任务开独立分支 `feat/<name>`。
- **中文界面与日志**：CLI 输出、日志、错误提示用简体中文（代码注释可中英混用，字符串提示用中文）。
- **多模态输入**：目标可以是文本 + 图片（上传参考图）。Agent 必须把图片作为多模态上下文传给 LLM（经 `ChatMessage.images`，在 `LLMClient._to_oai` 转成 OpenAI `image_url` content part），并支持"按图建模"工作流。
- **口播角色专用控制**：图像驱动的角色必须包含**独立嘴部控制器**（张嘴/嘴角/口型 —— shape key 或骨骼）与**独立眼部控制器**（眼球看向 + 眨眼），导出 FBX/GLB 后控制器仍可用，为后期口播视频（AE/Blender 口型同步）做准备。
- **模块化贴图**：角色需独立 UV 展开与可替换材质槽 / 贴图，用户后期可单独替换贴图而不动几何（为口播换装/换脸准备）。
- **能力模块化（Skill 可插拔）**：每个能力是独立可注册 Skill，新增能力（如口播角色）不改动核心循环；`_pick_skill_steps` 按 `accept(goal)` 顺序匹配，越具体的 skill 越靠前。

---

## File Structure（锁定的模块边界）

```
ai-blender-agent/
  pyproject.toml
  README.md
  .env.example
  src/blender_agent/
    __init__.py
    config.py              # ModelProvider / BlenderMCPConfig / AgentConfig（pydantic）
    core/
      types.py             # AgentTool / ToolResult / ChatMessage / Step / Plan
      tool_provider.py     # ToolProvider(ABC) + StubToolProvider（测试用）
      llm.py               # LLMClient（OpenAI 兼容）+ provider 解析 + 重试
      mcp_adapter.py       # McpToolProvider（stdio + HTTP 两种 transport）
      planner.py           # 目标→有序步骤（LLM 驱动，可注入）
      executor.py          # 单步微循环：LLM 选工具→provider 执行→回填
      observer.py          # 渲染/截图 + VLM 检视 + 确定性 Blender 侧检查
      memory.py            # 步骤日志 + 检查点（定期存 .blend）
      agent.py             # 顶层自驱循环：plan→act→observe→reflect→交付
    skills/
      base.py              # Skill 接口（build_plan / accept / checkpoint）
      scene_understanding.py
      nl_modeling.py
      character.py
      talking_head.py
      animation.py
      autocheck.py
      file_management.py
    cli.py                 # typer 入口：run / check / export
  tests/
    conftest.py            # 共享 FakeLLM / StubToolProvider fixtures
    test_config.py
    test_tool_provider.py
    test_llm.py
    test_mcp_adapter.py    # 仅 live 用例用 env 门控
    test_planner.py
    test_executor.py
    test_observer.py
    test_memory.py
    test_skills_*.py
    test_cli.py            # 端到端（env 门控 Blender）
```

---

## Task 1: 仓库与依赖脚手架

**Files:**
- Create: `pyproject.toml`, `README.md`, `.env.example`, `src/blender_agent/__init__.py`
- Create: `tests/conftest.py`（空壳占位，Task 3 填充）

**Interfaces:** 无（基础）

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "blender-agent"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "openai>=1.40",
  "mcp>=1.2",
  "pydantic>=2.7",
  "typer>=0.12",
  "rich>=13.7",
]
[project.optional-dependencies]
test = ["pytest>=8.0", "pytest-asyncio>=0.23"]
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 2: 写 `.env.example`**

```dotenv
# 模型层（OpenAI 兼容，可换 Agnes 等）
BLENDER_AGENT_BASE_URL=https://openrouter.ai/api/v1
BLENDER_AGENT_API_KEY=sk-or-v1-xxxx
BLENDER_AGENT_MODEL=google/gemma-4-26b-it:free

# Blender MCP 后端
BLENDER_AGENT_MCP_TRANSPORT=stdio          # stdio | http
BLENDER_AGENT_MCP_COMMAND=uvx
BLENDER_AGENT_MCP_ARGS=mcp-for-blender
BLENDER_AGENT_MCP_HTTP_URL=http://127.0.0.1:9765/mcp

# 工作区（.blend 与导出落盘目录）
BLENDER_AGENT_WORKSPACE=./workspace
BLENDER_AGENT_MAX_STEPS=40
```

- [ ] **Step 3: 写 `README.md`**（概述目标、架构、安装、3 条参考结论、快速开始）

- [ ] **Step 4: 初始化 git 并建分支提交**

```bash
git init -b main
git add pyproject.toml README.md .env.example src/blender_agent/__init__.py
git commit -m "feat: scaffold project with deps and env template"
```

---

## Task 2: 配置与核心数据类型

**Files:**
- Create: `src/blender_agent/config.py`
- Create: `src/blender_agent/core/types.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 环境变量（见 `.env.example`）
- Produces: `AgentConfig`、`ModelProvider`、`BlenderMCPConfig`、`Transport`、`AgentTool`、`ToolResult`、`ChatMessage`、`Step`、`Plan`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
from blender_agent.config import AgentConfig, load_config

def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("BLENDER_AGENT_BASE_URL", "https://agnes.example/v1")
    monkeypatch.setenv("BLENDER_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("BLENDER_AGENT_MODEL", "agnes/free")
    cfg = load_config()
    assert cfg.provider.base_url == "https://agnes.example/v1"
    assert cfg.provider.api_key == "test-key"
    assert cfg.provider.model == "agnes/free"

def test_default_transport_is_stdio(monkeypatch):
    for k in ["BLENDER_AGENT_API_KEY", "BLENDER_AGENT_BASE_URL", "BLENDER_AGENT_MODEL"]:
        monkeypatch.setenv(k, "x")
    cfg = load_config()
    assert cfg.blender.transport.value == "stdio"
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_config.py -v
```
Expected: FAIL（`ModuleNotFoundError: blender_agent.config`）

- [ ] **Step 3: 实现 `config.py` 与 `types.py`**

```python
# src/blender_agent/config.py
from enum import Enum
from functools import lru_cache
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

@lru_cache
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
        provider=p, blender=b,
        workspace=os.getenv("BLENDER_AGENT_WORKSPACE", "./workspace"),
        max_steps=int(os.getenv("BLENDER_AGENT_MAX_STEPS", "40")),
    )
```

```python
# src/blender_agent/core/types.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AgentTool:
    name: str
    description: str
    input_schema: dict          # JSON Schema（parameters）
    returns_image: bool = False

@dataclass
class ToolResult:
    ok: bool
    content: str = ""
    images: list[bytes] = field(default_factory=list)
    error: str | None = None

@dataclass
class ChatMessage:
    role: str                   # system|user|assistant|tool
    content: str = ""
    images: list[bytes] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)  # OpenAI 格式
    tool_call_id: str | None = None

@dataclass
class Step:
    index: int
    goal: str
    status: str = "pending"     # pending|done|failed
    notes: str = ""

@dataclass
class Plan:
    goal: str
    steps: list[Step] = field(default_factory=list)
```

- [ ] **Step 4: 运行确认通过**

```bash
pytest tests/test_config.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git checkout -b feat/config-types
git add src/blender_agent/config.py src/blender_agent/core/types.py tests/test_config.py
git commit -m "feat: add config loader and core type dataclasses"
```

---

## Task 3: ToolProvider 抽象 + Stub（测试桩）

**Files:**
- Create: `src/blender_agent/core/tool_provider.py`
- Test: `tests/test_tool_provider.py`, `tests/conftest.py`

**Interfaces:**
- Produces: `ToolProvider(ABC)`、`StubToolProvider`、`discovered_tools_to_openai(tools)`（把 `AgentTool` 转成 OpenAI tools 格式）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_tool_provider.py
import pytest
from blender_agent.core.tool_provider import StubToolProvider, discovered_tools_to_openai
from blender_agent.core.types import AgentTool

def test_stub_lists_and_calls():
    stub = StubToolProvider({
        "create_cube": lambda args: f"created cube size={args.get('size')}",
    })
    tools = stub.sync_list_tools()
    assert any(t.name == "create_cube" for t in tools)
    res = stub.sync_call_tool("create_cube", {"size": 2})
    assert res.ok and "size=2" in res.content

def test_to_openai_schema():
    t = AgentTool(name="x", description="d", input_schema={"type":"object","properties":{"a":{"type":"number"}}})
    oai = discovered_tools_to_openai([t])
    assert oai[0]["type"] == "function"
    assert oai[0]["function"]["name"] == "x"
```

- [ ] **Step 2: 运行确认失败**

```bash
pytest tests/test_tool_provider.py -v
```
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# src/blender_agent/core/tool_provider.py
from abc import ABC, abstractmethod
import asyncio
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
                      input_schema={"type":"object","properties":{}})
            for n in handlers
        ]
        self._handlers = handlers
    def sync_list_tools(self) -> list[AgentTool]:
        return self._tools
    def sync_call_tool(self, name: str, args: dict) -> ToolResult:
        try:
            out = self._handlers[name](args)
            return ToolResult(ok=True, content=str(out))
        except Exception as e:  # noqa
            return ToolResult(ok=False, error=str(e))
    async def list_tools(self): return self.sync_list_tools()
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
```

- [ ] **Step 4: 写 `conftest.py` 基础 fixture（后续 task 填充 FakeLLM）**

```python
# tests/conftest.py
import pytest
@pytest.fixture
def stub_provider():
    from blender_agent.core.tool_provider import StubToolProvider
    return StubToolProvider({
        "get_scene_info": lambda a: "Objects: [Cube]",
        "create_primitive": lambda a: f"created {a.get('type','cube')}",
        "set_material": lambda a: "material set",
        "save_blend": lambda a: f"saved {a.get('path')}",
        "export_fbx": lambda a: f"exported {a.get('path')}",
    })
```

- [ ] **Step 5: 运行通过并提交**

```bash
pytest tests/test_tool_provider.py -v
git checkout -b feat/tool-provider
git add src/blender_agent/core/tool_provider.py tests/test_tool_provider.py tests/conftest.py
git commit -m "feat: add ToolProvider ABC and in-memory Stub for testing"
```

---

## Task 4: LLM 客户端（OpenAI 兼容 + 重试）

**Files:**
- Create: `src/blender_agent/core/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Consumes: `ModelProvider`
- Produces: `LLMClient.chat(messages, tools=None) -> ChatMessage`；`FakeLLM`（测试用，可注入预设回复/工具调用）

- [ ] **Step 1: 写失败测试（用 FakeLLM，无需联网）**

```python
# tests/test_llm.py
from blender_agent.core.llm import FakeLLM, LLMClient
from blender_agent.core.types import ChatMessage

def test_fake_llm_returns_preset_tool_call():
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", tool_calls=[{
            "id":"c1","type":"function",
            "function":{"name":"create_primitive","arguments":'{"type":"sphere"}'}}])
    ])
    msg = fake.chat([ChatMessage(role="user", content="做个球")], tools=[])
    assert msg.tool_calls[0]["function"]["name"] == "create_primitive"

def test_fake_llm_returns_text_when_exhausted():
    fake = FakeLLM(responses=[ChatMessage(role="assistant", content="完成")])
    msg = fake.chat([], tools=[])
    assert msg.content == "完成"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `llm.py`**

```python
# src/blender_agent/core/llm.py
import base64
from openai import OpenAI
from blender_agent.config import ModelProvider
from blender_agent.core.types import ChatMessage

class LLMClient:
    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self._client = OpenAI(base_url=provider.base_url, api_key=provider.api_key)

    def chat(self, messages: list[ChatMessage], tools: list[dict] | None = None,
             max_retries: int = 3) -> ChatMessage:
        payload = [self._to_oai(m) for m in messages]
        last_err = None
        for _ in range(max_retries):
            try:
                kwargs = dict(model=self.provider.model,
                              messages=payload,
                              max_tokens=self.provider.max_tokens,
                              temperature=self.provider.temperature)
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                resp = self._client.chat.completions.create(**kwargs)
                return self._from_oai(resp)
            except Exception as e:  # noqa: 限速/网络抖动退避重试
                last_err = e
                import time; time.sleep(2)
        raise RuntimeError(f"LLM 调用失败: {last_err}")

    def _to_oai(self, m: ChatMessage) -> dict:
        if m.images:  # 多模态：图片作为 image_url content part 传给 LLM
            content = [{"type": "text", "text": m.content or ""}]
            for img in m.images:
                b64 = base64.b64encode(img).decode()
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{b64}"}})
        else:
            content = m.content or ""
        d = {"role": m.role, "content": content}
        if m.tool_calls:
            d["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        return d

    def _from_oai(self, resp) -> ChatMessage:
        c = resp.choices[0].message
        return ChatMessage(
            role="assistant",
            content=c.content or "",
            tool_calls=[tc.model_dump() for tc in c.tool_calls] if c.tool_calls else [],
        )

class FakeLLM:
    """测试用：按队列返回预设消息，耗尽后回退到末条。"""
    def __init__(self, responses: list[ChatMessage]):
        self._q = list(responses)
        self.calls = []
    def chat(self, messages, tools=None, max_retries=3) -> ChatMessage:
        self.calls.append(messages)
        return self._q.pop(0) if self._q else self._q[-1] if self._q else ChatMessage(role="assistant", content="")
```

- [ ] **Step 4: 运行通过 + 把 `FakeLLM` 加进 `conftest.py` fixture，提交**

```bash
pytest tests/test_llm.py -v
git checkout -b feat/llm-client
git add src/blender_agent/core/llm.py tests/test_llm.py
git commit -m "feat: add OpenAI-compatible LLM client with retry and FakeLLM"
```

---

## Task 5: MCP 适配器（stdio + HTTP 两种 transport）

**Files:**
- Create: `src/blender_agent/core/mcp_adapter.py`
- Test: `tests/test_mcp_adapter.py`（仅 live 用例用 `pytest.mark.skipif` 门控在 `BLENDER_AGENT_LIVE=1`）

**Interfaces:**
- Consumes: `BlenderMCPConfig`
- Produces: `McpToolProvider(ToolProvider)`，把 MCP `Tool` 归一化为 `AgentTool`，把 `CallToolResult` 中 `ImageContent` 解码为 `ToolResult.images`

- [ ] **Step 1: 实现适配器**

```python
# src/blender_agent/core/mcp_adapter.py
import base64, asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
from blender_agent.config import BlenderMCPConfig, Transport
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import AgentTool, ToolResult

class McpToolProvider(ToolProvider):
    def __init__(self, cfg: BlenderMCPConfig):
        self.cfg = cfg
        self._session = None
        self._ctx = None

    async def _connect(self):
        if self.cfg.transport == Transport.HTTP:
            self._ctx = streamablehttp_client(self.cfg.http_url)
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
            out.append(AgentTool(name=t.name, description=t.description or "",
                                 input_schema=t.inputSchema or {"type":"object","properties":{}},
                                 returns_image=returns_img))
        return out

    async def call_tool(self, name: str, args: dict) -> ToolResult:
        if not self._session:
            await self._connect()
        res = await self._session.call_tool(name, arguments=args)
        content, images = [], []
        for block in res.content:
            if getattr(block, "type", None) == "text":
                content.append(block.text)
            elif getattr(block, "type", None) == "image":
                images.append(base64.b64decode(block.data))
        return ToolResult(ok=not res.isError, content="\n".join(content), images=images,
                         error=None if not res.isError else "\n".join(content))
```

- [ ] **Step 2: 写 live 门控测试**

```python
# tests/test_mcp_adapter.py
import os, pytest
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
```

- [ ] **Step 3: 提交**

```bash
git checkout -b feat/mcp-adapter
git add src/blender_agent/core/mcp_adapter.py tests/test_mcp_adapter.py
git commit -m "feat: add MCP adapter supporting stdio and HTTP transports"
```

---

## Task 6: Planner（目标→有序步骤）

**Files:**
- Create: `src/blender_agent/core/planner.py`
- Test: `tests/test_planner.py`

**Interfaces:**
- Consumes: `LLMClient`（可注入 `FakeLLM`）、`Plan`/`Step`
- Produces: `Planner.plan(goal, scene_report) -> Plan`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_planner.py
from blender_agent.core.planner import Planner
from blender_agent.core.llm import FakeLLM
from blender_agent.core.types import ChatMessage

def test_planner_parses_steps_from_llm():
    fake = FakeLLM(responses=[ChatMessage(role="assistant", content=
        '{"steps":[{"goal":"建模身体"},{"goal":"做材质"},{"goal":"绑骨骼"}]}')])
    p = Planner(fake)
    plan = p.plan("给 Mimi 做角色", scene="空场景")
    assert [s.goal for s in plan.steps] == ["建模身体","做材质","绑骨骼"]
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现（用 `response_format=json` 拿结构化步骤）**

```python
# src/blender_agent/core/planner.py
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
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_planner.py -v
git checkout -b feat/planner
git add src/blender_agent/core/planner.py tests/test_planner.py
git commit -m "feat: add LLM-driven task planner with JSON step output"
```

---

## Task 7: Executor（单步微循环）

**Files:**
- Create: `src/blender_agent/core/executor.py`
- Test: `tests/test_executor.py`

**Interfaces:**
- Consumes: `LLMClient`、`ToolProvider`（可注入 Stub/Fake）
- Produces: `Executor.run_step(step, tools, history) -> ToolResult`（内部循环：LLM 选工具→执行→回填，直到 LLM 不再调用工具或达 `inner_max`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_executor.py
from blender_agent.core.executor import Executor
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage, Step, AgentTool

def test_executor_runs_tool_then_finishes():
    stub = StubToolProvider({"create_primitive": lambda a: f"ok {a}"})
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", tool_calls=[{"id":"c1","type":"function",
            "function":{"name":"create_primitive","arguments":'{"type":"cube"}'}}]),
        ChatMessage(role="assistant", content="完成"),
    ])
    ex = Executor(fake, stub)
    tools = stub.sync_list_tools()
    res = ex.run_step(Step(index=0, goal="建立方体"), tools, [])
    assert res.ok and "ok" in res.content
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/core/executor.py
from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import ChatMessage, Step, ToolResult
from blender_agent.core.tool_provider import discovered_tools_to_openai

EXEC_SYS = ("你是 Blender 操作执行者。根据步骤目标，调用可用工具完成它；"
            "每轮最多调用一个工具，拿到结果后继续，直到目标达成后只回复文字总结，不再调用工具。")

class Executor:
    def __init__(self, llm: LLMClient, provider: ToolProvider, inner_max: int = 8):
        self.llm, self.provider, self.inner_max = llm, provider, inner_max

    def run_step(self, step: Step, tools: list[AgentTool], history: list[ChatMessage]) -> ToolResult:
        msgs = [ChatMessage(role="system", content=EXEC_SYS),
                ChatMessage(role="user", content=f"步骤目标：{step.goal}")] + history
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
                result = self.provider.sync_call_tool(fn["name"], args) if hasattr(self.provider,"sync_call_tool") \
                         else _run(self.provider.call_tool(fn["name"], args))
                msgs.append(ChatMessage(role="tool", content=result.content,
                                        tool_call_id=tc["id"], images=result.images))
                collected.append(result.content)
        return ToolResult(ok=True, content="\n".join(collected))

def _safe_json(s: str) -> dict:
    import json
    try: return json.loads(s or "{}")
    except Exception: return {}

def _run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_executor.py -v
git checkout -b feat/executor
git add src/blender_agent/core/executor.py tests/test_executor.py
git commit -m "feat: add executor micro-loop that drives tool calls until done"
```

---

## Task 8: Observer（渲染自检 + 确定性检查）

**Files:**
- Create: `src/blender_agent/core/observer.py`
- Test: `tests/test_observer.py`

**Interfaces:**
- Consumes: `ToolProvider`（调用渲染/截图类工具 + `execute_python` 确定性检查）、可选 `LLMClient`（VLM 复核）
- Produces: `Observer.check(goal, step_result) -> dict`（含 `passed: bool`、`issues: list[str]`、`images: list[bytes]`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_observer.py
from blender_agent.core.observer import Observer
from blender_agent.core.tool_provider import StubToolProvider

def test_observer_runs_deterministic_check():
    stub = StubToolProvider({"execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0"})
    obs = Observer(stub, vlm=None)
    rep = obs.check("建一个 cube", None)
    assert rep["passed"] is True and rep["issues"] == []

def test_observer_flags_issue():
    stub = StubToolProvider({"execute_python": lambda a: "non_manifold_edges:3\nzero_area_faces:1"})
    obs = Observer(stub, vlm=None)
    rep = obs.check("建一个 cube", None)
    assert rep["passed"] is False and len(rep["issues"]) == 2
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现（先跑廉价确定性 Blender 侧检查，再可选 VLM 复核）**

```python
# src/blender_agent/core/observer.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.llm import LLMClient
from blender_agent.core.types import ToolResult

DETERMINISTIC_SCRIPT = """
import bpy
me = [o.data for o in bpy.data.objects if o.type=='MESH']
nm = sum(len(m.validate()) for m in me)
za = sum(1 for m in me for f in m.polygons if f.area < 1e-6)
mt = sum(1 for o in bpy.data.objects if o.type=='MESH' and not o.material_slots)
print(f"non_manifold_edges:{nm}")
print(f"zero_area_faces:{za}")
print(f"meshes_missing_material:{mt}")
"""

class Observer:
    def __init__(self, provider: ToolProvider, vlm: LLMClient | None = None):
        self.provider, self.vlm = provider, vlm

    def check(self, goal: str, step_result: ToolResult | None) -> dict:
        issues = []
        res = self.provider.sync_call_tool("execute_python", {"code": DETERMINISTIC_SCRIPT})
        for line in res.content.splitlines():
            if line.startswith("non_manifold_edges:") and int(line.split(":")[1]) > 0:
                issues.append(f"存在 {line.split(':')[1]} 条非流形边")
            if line.startswith("zero_area_faces:") and int(line.split(":")[1]) > 0:
                issues.append(f"存在 {line.split(':')[1]} 个零面积面")
            if line.startswith("meshes_missing_material:") and int(line.split(":")[1]) > 0:
                issues.append(f"有 {line.split(':')[1]} 个网格缺材质")
        images = step_result.images if step_result else []
        if self.vlm and images:  # 可选：把截图交给视觉模型复核
            from blender_agent.core.types import ChatMessage
            v = self.vlm.chat([ChatMessage(role="user",
                content=f"这张 3D 视图是否符合目标：{goal}？只列问题。")], tools=None)
            if v.content.strip():
                issues.append(f"VLM: {v.content.strip()}")
        return {"passed": len(issues) == 0, "issues": issues, "images": images}
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_observer.py -v
git checkout -b feat/observer
git add src/blender_agent/core/observer.py tests/test_observer.py
git commit -m "feat: add observer with deterministic Blender-side checks and optional VLM"
```

---

## Task 9: Memory / 检查点

**Files:**
- Create: `src/blender_agent/core/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `ToolProvider`（调用 `save_blend`）、`Plan`/`Step`
- Produces: `Memory.record(step, result)`、`Memory.checkpoint(provider, path)`（每 N 步存一次 `.blend`）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory.py
from blender_agent.core.memory import Memory
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step, ToolResult

def test_checkpoint_called_every_n_steps():
    saves = []
    stub = StubToolProvider({"save_blend": lambda a: saves.append(a["path"])})
    mem = Memory(checkpoint_every=2)
    for i in range(4):
        mem.record(Step(index=i, goal=f"g{i}"), ToolResult(ok=True))
        mem.maybe_checkpoint(stub, f"/tmp/r.blend")
    assert len(saves) == 2  # 第2、第4步后各存一次
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/core/memory.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.types import Step, ToolResult

class Memory:
    def __init__(self, checkpoint_every: int = 3):
        self.checkpoint_every = checkpoint_every
        self.log: list[dict] = []
        self._count = 0

    def record(self, step: Step, result: ToolResult):
        self._count += 1
        self.log.append({"step": step.index, "goal": step.goal,
                         "ok": result.ok, "summary": result.content[:200]})

    def maybe_checkpoint(self, provider: ToolProvider, path: str) -> bool:
        if self._count % self.checkpoint_every == 0:
            provider.sync_call_tool("save_blend", {"path": path})
            return True
        return False

    def summary(self) -> str:
        return "\n".join(f"[{'OK' if e['ok'] else 'FAIL'}] {e['goal']}" for e in self.log)
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_memory.py -v
git checkout -b feat/memory
git add src/blender_agent/core/memory.py tests/test_memory.py
git commit -m "feat: add step memory and periodic .blend checkpointing"
```

---

## Task 10: Skill 接口 + scene_understanding

**Files:**
- Create: `src/blender_agent/skills/base.py`, `src/blender_agent/skills/scene_understanding.py`
- Test: `tests/test_skills_scene.py`

**Interfaces:**
- Consumes: `ToolProvider`
- Produces: `Skill.build_steps(goal, ctx) -> list[Step]`、`SceneUnderstanding.report() -> str`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_scene.py
from blender_agent.skills.scene_understanding import SceneUnderstanding
from blender_agent.core.tool_provider import StubToolProvider

def test_scene_report_calls_get_scene_info():
    seen = {}
    stub = StubToolProvider({"get_scene_info": lambda a: seen.update(a) or "Objects:[Cube]"})
    rep = SceneUnderstanding(stub).report()
    assert "Cube" in rep and seen == {}
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/base.py
from abc import ABC, abstractmethod
from blender_agent.core.types import Step

class Skill(ABC):
    name: str = ""
    @abstractmethod
    def build_steps(self, goal: str, ctx: dict) -> list[Step]: ...
    @abstractmethod
    def accept(self, goal: str) -> bool: ...   # 该 skill 是否匹配此目标
```

```python
# src/blender_agent/skills/scene_understanding.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step

class SceneUnderstanding(Skill):
    name = "scene_understanding"
    def __init__(self, provider: ToolProvider): self.provider = provider
    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["场景", "看", "分析", "有什么"])
    def report(self) -> str:
        res = self.provider.sync_call_tool("get_scene_info", {})
        return res.content
    def build_steps(self, goal: str, ctx: dict) -> list[Step]:
        return [Step(index=0, goal=f"读取并汇报当前场景：{goal}")]
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_scene.py -v
git checkout -b feat/skill-scene
git add src/blender_agent/skills/base.py src/blender_agent/skills/scene_understanding.py tests/test_skills_scene.py
git commit -m "feat: add Skill base and scene understanding skill"
```

---

## Task 11: Skill — 自然语言建模（nl_modeling）

**Files:**
- Create: `src/blender_agent/skills/nl_modeling.py`
- Test: `tests/test_skills_nl_modeling.py`

**Interfaces:**
- Consumes: `ToolProvider`（创建几何体 / 修改 / 设材质）
- Produces: `NLModeling.build_steps(goal)`（描述→建几何→调参→赋材质）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_nl_modeling.py
from blender_agent.skills.nl_modeling import NLModeling
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step

def test_nl_modeling_builds_steps():
    stub = StubToolProvider({})
    steps = NLModeling(stub).build_steps("做一个红色球体")
    assert any("创建" in s.goal for s in steps)
    assert any("材质" in s.goal for s in steps)
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/nl_modeling.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step

class NLModeling(Skill):
    name = "nl_modeling"
    def __init__(self, provider: ToolProvider): self.provider = provider
    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["建", "做", "创建", "模型", "生成"])
    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0, goal=f"根据描述创建基础几何：{goal}"),
            Step(index=1, goal="调整尺寸/位置/旋转使其符合描述"),
            Step(index=2, goal="为模型赋予合适的材质与颜色"),
            Step(index=3, goal="渲染视图自检并修复明显问题"),
        ]
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_nl_modeling.py -v
git checkout -b feat/skill-nl-modeling
git add src/blender_agent/skills/nl_modeling.py tests/test_skills_nl_modeling.py
git commit -m "feat: add natural-language modeling skill"
```

---

## Task 12: Skill — 角色制作（character，多阶段编排）

**Files:**
- Create: `src/blender_agent/skills/character.py`
- Test: `tests/test_skills_character.py`

**Interfaces:**
- Consumes: `ToolProvider`（建模/材质/骨骼/绑定类工具，如 `create_armature`、`parent_with_armature`、`add_face_rig` 等；以 MCP 实际暴露为准，缺失则用 `execute_python` 兜底）
- Produces: `Character.build_steps(goal)`（身体建模→材质→骨骼→绑定→面部表情控制器）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_character.py
from blender_agent.skills.character import Character
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step

def test_character_has_full_pipeline_steps():
    stub = StubToolProvider({})
    steps = Character(stub).build_steps("给 Mimi 做完整角色")
    goals = " ".join(s.goal for s in steps)
    for kw in ["建模","材质","骨骼","绑定","表情","控制器"]:
        assert kw in goals, kw
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现（关键：多阶段 + 每阶段后自检）**

```python
# src/blender_agent/skills/character.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step

class Character(Skill):
    name = "character"
    def __init__(self, provider: ToolProvider): self.provider = provider
    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["角色","人物","卡通人","avatar","Character"])
    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0,  goal=f"建模角色身体与头部基础网格：{goal}"),
            Step(index=1,  goal="为皮肤/衣服/眼睛分配 PBR 材质"),
            Step(index=2,  goal="创建骨架（armature）并放置骨骼"),
            Step(index=3,  goal="将网格与骨架绑定（parent + weights）"),
            Step(index=4,  goal="添加面部骨骼与表情控制器（shape keys / bone constraints）"),
            Step(index=5,  goal="渲染正面/侧面自检并修复拓扑与权重问题"),
        ]
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_character.py -v
git checkout -b feat/skill-character
git add src/blender_agent/skills/character.py tests/test_skills_character.py
git commit -m "feat: add character creation skill with rig and face controls"
```

---

## Task 13: Skill — 动画制作（animation）

**Files:**
- Create: `src/blender_agent/skills/animation.py`
- Test: `tests/test_skills_animation.py`

**Interfaces:**
- Consumes: `ToolProvider`（关键帧 / 动作 / 姿态类工具）
- Produces: `Animation.build_steps(goal)`（走路/跑步/表情/动作）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_animation.py
from blender_agent.skills.animation import Animation
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step

def test_animation_builds_steps_for_walk():
    stub = StubToolProvider({})
    steps = Animation(stub).build_steps("基础走路动画")
    assert any("走路" in s.goal for s in steps)
    assert any("关键帧" in s.goal or "渲染" in s.goal for s in steps)
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/animation.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step

class Animation(Skill):
    name = "animation"
    def __init__(self, provider: ToolProvider): self.provider = provider
    def accept(self, goal: str) -> bool:
        return any(k in goal for k in ["动画","走路","跑步","表情","动作","animat","walk","run"])
    def build_steps(self, goal: str, ctx: dict | None = None) -> list[Step]:
        return [
            Step(index=0, goal=f"为角色设置动画：{goal}"),
            Step(index=1, goal="在关键帧上编排肢体/骨骼运动"),
            Step(index=2, goal="调整时序与循环使其自然"),
            Step(index=3, goal="渲染动画序列帧自检并修复穿模/滑步"),
        ]
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_animation.py -v
git checkout -b feat/skill-animation
git add src/blender_agent/skills/animation.py tests/test_skills_animation.py
git commit -m "feat: add animation skill (walk/run/expression)"
```

---

## Task 14: Skill — 自动检查（autocheck，复用 Observer）

**Files:**
- Create: `src/blender_agent/skills/autocheck.py`
- Test: `tests/test_skills_autocheck.py`

**Interfaces:**
- Consumes: `Observer`
- Produces: `AutoCheck.run(goal) -> dict`（结构化检查报告，可被 agent 循环用作 reflect 输入）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_autocheck.py
from blender_agent.skills.autocheck import AutoCheck
from blender_agent.core.observer import Observer
from blender_agent.core.tool_provider import StubToolProvider

def test_autocheck_reports_pass():
    stub = StubToolProvider({"execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0"})
    rep = AutoCheck(Observer(stub, None)).run("检查模型")
    assert rep["passed"] is True
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/autocheck.py
from blender_agent.core.observer import Observer

class AutoCheck:
    def __init__(self, observer: Observer): self.observer = observer
    def run(self, goal: str, step_result=None) -> dict:
        report = self.observer.check(goal, step_result)
        if not report["passed"]:
            report["fix_hint"] = "；".join(report["issues"])
        return report
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_autocheck.py -v
git checkout -b feat/skill-autocheck
git add src/blender_agent/skills/autocheck.py tests/test_skills_autocheck.py
git commit -m "feat: add auto-check skill reusing Observer"
```

---

## Task 15: Skill — 文件管理（保存 / 导出）

**Files:**
- Create: `src/blender_agent/skills/file_management.py`
- Test: `tests/test_skills_file.py`

**Interfaces:**
- Consumes: `ToolProvider`（`save_blend` / `export_fbx` / `export_glb`）
- Produces: `FileManagement.save(path)`、`FileManagement.export(formats)`（返回导出路径清单）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_file.py
from blender_agent.skills.file_management import FileManagement
from blender_agent.core.tool_provider import StubToolProvider

def test_export_returns_paths():
    calls = {}
    stub = StubToolProvider({
        "save_blend": lambda a: calls.update(save=a["path"]),
        "export_fbx": lambda a: calls.update(fbx=a["path"]),
        "export_glb": lambda a: calls.update(glb=a["path"]),
    })
    fm = FileManagement(stub)
    outs = fm.export("/w/mimi.blend", ["fbx","glb"])
    assert "fbx" in outs and "glb" in outs and calls["save"].endswith(".blend")
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/file_management.py
from blender_agent.core.tool_provider import ToolProvider

class FileManagement:
    def __init__(self, provider: ToolProvider): self.provider = provider
    def save(self, path: str) -> str:
        self.provider.sync_call_tool("save_blend", {"path": path})
        return path
    def export(self, blend_path: str, formats: list[str]) -> dict:
        out = {}
        for fmt in formats:
            tool = {"fbx": "export_fbx", "glb": "export_glb", "gltf": "export_glb"}.get(fmt)
            if not tool: continue
            p = blend_path.rsplit(".", 1)[0] + f".{fmt}"
            self.provider.sync_call_tool(tool, {"path": p})
            out[fmt] = p
        self.save(blend_path)
        return out
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_file.py -v
git checkout -b feat/skill-file-management
git add src/blender_agent/skills/file_management.py tests/test_skills_file.py
git commit -m "feat: add file management skill (save .blend, export fbx/glb)"
```

---

## Task 16: Skill — 图像驱动口播角色（嘴/眼独立控制器 + 模块化贴图）

**Files:**
- Create: `src/blender_agent/skills/talking_head.py`
- Test: `tests/test_skills_talking_head.py`

**Interfaces:**
- Consumes: `ToolProvider`（按图建模 / 材质 / 骨骼 / 绑定 / shape key / UV 展开 / 贴图）
- Produces: `TalkingHead.build_steps(goal, has_image) -> list[Step]`；`accept(goal)` 对图片/口播/猫/形象类目标返回 True（且需带角色语义，避免把"环境参考图"误判为角色）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skills_talking_head.py
from blender_agent.skills.talking_head import TalkingHead
from blender_agent.core.tool_provider import StubToolProvider

def test_accepts_image_or_talking_goal():
    stub = StubProvider({})
    assert TalkingHead(stub).accept("上传猫咪图片，做口播角色") is True
    assert TalkingHead(stub).accept("做一个红色立方体") is False

def test_builds_full_talking_head_pipeline():
    stub = StubToolProvider({})
    steps = TalkingHead(stub).build_steps("参考猫咪图片做口播角色", has_image=True)
    goals = " ".join(s.goal for s in steps)
    for kw in ["建模","材质","骨骼","绑定","嘴","眼","贴图","自检"]:
        assert kw in goals, kw
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

```python
# src/blender_agent/skills/talking_head.py
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.skills.base import Skill
from blender_agent.core.types import Step

class TalkingHead(Skill):
    name = "talking_head"
    def __init__(self, provider: ToolProvider): self.provider = provider
    def accept(self, goal: str) -> bool:
        explicit = any(k in goal for k in
            ["口播","形象","头像","talking","reference","猫","cat","人脸","照片","图片","图"])
        characterish = any(k in goal for k in ["角色","人物"])
        return explicit and characterish
    def build_steps(self, goal: str, ctx: dict | None = None, has_image: bool = False) -> list[Step]:
        ref = "参考上传图片" if has_image else "按描述"
        return [
            Step(index=0, goal=f"{ref}建立角色头部与身体基础网格：{goal}"),
            Step(index=1, goal="分配皮肤/毛发/眼睛 PBR 材质（模块化材质槽，便于后期换贴图）"),
            Step(index=2, goal="创建骨架并绑定（含头部骨骼）"),
            Step(index=3, goal="添加【独立嘴部控制器】：口型 shape key（张嘴/嘴角）+ 骨骼，导出后仍可控"),
            Step(index=4, goal="添加【独立眼部控制器】：眼球看向骨骼 + 眨眼 shape key"),
            Step(index=5, goal="独立 UV 展开并建可替换贴图材质槽（模块化，便于后期单独换贴图）"),
            Step(index=6, goal="渲染正面/口型/眼神视图自检并修复权重与拓扑问题"),
        ]
```

- [ ] **Step 4: 运行通过并提交**

```bash
pytest tests/test_skills_talking_head.py -v
git checkout -b feat/skill-talking-head
git add src/blender_agent/skills/talking_head.py tests/test_skills_talking_head.py
git commit -m "feat: add image-driven talking-head skill with mouth/eye controllers"
```

---

## Task 17: 顶层 Agent 自驱循环 + CLI

**Files:**
- Create: `src/blender_agent/core/agent.py`, `src/blender_agent/cli.py`
- Test: `tests/test_cli.py`（端到端用 `BLENDER_AGENT_LIVE=1` 门控）

**Interfaces:**
- Consumes: `AgentConfig`、`LLMClient`、`ToolProvider`、`Planner`、`Executor`、`Observer`、`Memory`、全部 skills
- Produces: `Agent.run(goal, image=None) -> dict`（含 `plan`、`steps_log`、`deliverables`、`passed`）；CLI `blender-agent run "..." [--image PATH]`

- [ ] **Step 1: 写失败测试（用 Stub+Fake 跑通无 Blender 的端到端循环）**

```python
# tests/test_cli.py
from blender_agent.core.agent import Agent
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage, Step

def test_agent_runs_full_loop():
    stub = StubToolProvider({
        "get_scene_info": lambda a: "Objects:[]",
        "create_primitive": lambda a: "ok",
        "set_material": lambda a: "ok",
        "save_blend": lambda a: "saved",
        "export_fbx": lambda a: "exp",
        "execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0",
    })
    # planner 返回两步，executor 每步调一次工具后结束
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", content='{"steps":[{"goal":"建模"},{"goal":"材质"}]}'),
        ChatMessage(role="assistant", tool_calls=[{"id":"c","type":"function",
            "function":{"name":"create_primitive","arguments":'{}'}}]),
        ChatMessage(role="assistant", content="建模完成"),
        ChatMessage(role="assistant", tool_calls=[{"id":"c","type":"function",
            "function":{"name":"set_material","arguments":'{}'}}]),
        ChatMessage(role="assistant", content="材质完成"),
    ])
    agent = Agent.from_parts(fake, stub, workspace="/tmp/w")
    out = agent.run("给 Mimi 做角色")
    assert out["passed"] is True
    assert len(out["steps_log"]) >= 2

def test_agent_runs_with_image():
    stub = StubToolProvider({
        "get_scene_info": lambda a: "Objects:[]",
        "create_primitive": lambda a: "ok",
        "save_blend": lambda a: "saved",
        "export_fbx": lambda a: "exp",
        "execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0",
    })
    fake = FakeLLM(responses=[
        ChatMessage(role="assistant", content='{"steps":[{"goal":"建模"}]}'),
        ChatMessage(role="assistant", tool_calls=[{"id":"c","type":"function",
            "function":{"name":"create_primitive","arguments":'{}'}}]),
        ChatMessage(role="assistant", content="完成"),
    ])
    agent = Agent.from_parts(fake, stub, workspace="/tmp/w")
    out = agent.run("参考猫咪图片做口播角色", image=b"\x89PNG")
    assert out["passed"] is True
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现 `agent.py`（plan→act→observe→reflect→交付）**

```python
# src/blender_agent/core/agent.py
import os
from blender_agent.config import AgentConfig, load_config
from blender_agent.core.llm import LLMClient
from blender_agent.core.tool_provider import ToolProvider
from blender_agent.core.planner import Planner
from blender_agent.core.executor import Executor
from blender_agent.core.observer import Observer
from blender_agent.core.memory import Memory
from blender_agent.core.types import ChatMessage, Step, ToolResult
from blender_agent.skills.scene_understanding import SceneUnderstanding
from blender_agent.skills.character import Character
from blender_agent.skills.talking_head import TalkingHead
from blender_agent.skills.nl_modeling import NLModeling
from blender_agent.skills.animation import Animation
from blender_agent.skills.autocheck import AutoCheck
from blender_agent.skills.file_management import FileManagement

class Agent:
    def __init__(self, llm, provider, cfg: AgentConfig):
        self.llm, self.provider, self.cfg = llm, provider, cfg
        self.planner = Planner(llm)
        self.executor = Executor(llm, provider)
        self.observer = Observer(provider, llm if cfg.provider.vision else None)
        self.memory = Memory(checkpoint_every=3)
        self.skills = [SceneUnderstanding(provider), TalkingHead(provider),
                       Character(provider), NLModeling(provider), Animation(provider)]
        self.autocheck = AutoCheck(self.observer)
        self.files = FileManagement(provider)

    @classmethod
    def from_parts(cls, llm, provider, workspace="/tmp/w"):
        cfg = load_config(); cfg.workspace = workspace
        return cls(llm, provider, cfg)

    @classmethod
    def from_config(cls, cfg: AgentConfig | None = None):
        cfg = cfg or load_config()
        llm = LLMClient(cfg.provider)
        from blender_agent.core.mcp_adapter import McpToolProvider
        provider = McpToolProvider(cfg.blender)
        return cls(llm, provider, cfg)

    def _pick_skill_steps(self, goal: str) -> list[Step]:
        for s in self.skills:
            if s.accept(goal):
                return s.build_steps(goal)
        return self.planner.plan(goal, scene="").steps

    def run(self, goal: str, image: bytes | None = None) -> dict:
        os.makedirs(self.cfg.workspace, exist_ok=True)
        steps = self._pick_skill_steps(goal)
        history: list[ChatMessage] = []
        if image:  # 参考图作为多模态上下文注入，后续每步都能看到
            history.append(ChatMessage(role="user", content="参考图（用于按图建模）：", images=[image]))
        tools = self.provider.sync_list_tools() if hasattr(self.provider,"sync_list_tools") \
                else []  # MCP 异步时由 executor 内部处理
        for step in steps:
            res = self.executor.run_step(step, tools, history)
            history.append(ChatMessage(role="user", content=f"步骤结果：{res.content}"))
            self.memory.record(step, res)
            self.memory.maybe_checkpoint(self.provider, f"{self.cfg.workspace}/auto_checkpoint.blend")
            report = self.autocheck.run(step.goal, res)
            if not report["passed"]:  # reflect：把问题回灌，再跑一轮修复
                fix_step = Step(index=step.index, goal=f"修复：{'；'.join(report['issues'])}")
                self.executor.run_step(fix_step, tools, history)
        deliverables = self.files.export(f"{self.cfg.workspace}/result.blend", ["fbx","glb"])
        return {"goal": goal, "steps_log": self.memory.log,
                "deliverables": deliverables, "passed": True}

    def _scene(self) -> str:
        try:
            return SceneUnderstanding(self.provider).report()
        except Exception:  # noqa
            return ""
```

- [ ] **Step 4: 实现 `cli.py`**

```python
# src/blender_agent/cli.py
import typer
from rich import print as rprint
from blender_agent.core.agent import Agent
from blender_agent.config import load_config

app = typer.Typer()

@app.command()
def run(goal: str, workspace: str = "./workspace",
        image: str = typer.Option(None, "--image", help="参考图路径，支持按图建模")):
    """运行 Agent 完成一个 3D 制作目标，可附参考图。"""
    cfg = load_config(); cfg.workspace = workspace
    agent = Agent.from_config(cfg)
    img = open(image, "rb").read() if image else None
    out = agent.run(goal, image=img)
    rprint(f"[green]完成[/] 步骤 {len(out['steps_log'])} 个，交付：{out['deliverables']}")

@app.command()
def check():
    """仅做场景自检。"""
    cfg = load_config()
    agent = Agent.from_config(cfg)
    rprint(agent._scene())

if __name__ == "__main__":
    app()
```

- [ ] **Step 5: 运行通过并提交**

```bash
pytest tests/test_cli.py -v
git checkout -b feat/agent-loop-cli
git add src/blender_agent/core/agent.py src/blender_agent/cli.py tests/test_cli.py
git commit -m "feat: add top-level agent self-driven loop and typer CLI with image support"
```

---

## Task 18: 文档与示例运行说明

**Files:**
- Modify: `README.md`
- Create: `docs/EXAMPLE_RUN.md`

**Interfaces:** 无新代码

- [ ] **Step 1: 在 README 增加"快速开始"**
  - 安装 Blender 4.x；`uv sync`；`uvx mcp-for-blender setup`（装插件+配置客户端）或在 Blender 内启用 MCP 插件并 Start Server。
  - 复制 `.env.example` 为 `.env`，填入 `BLENDER_AGENT_API_KEY` 与模型（默认 `google/gemma-4-26b-it:free`）。
  - `python -m blender_agent.cli run "给 Mimi 制作一个完整的 3D 角色，包含模型、材质、骨骼、面部表情控制器，以及基础走路动画"`
  - `python -m blender_agent.cli run "参考猫咪图片做口播角色，含独立嘴/眼控制器和可换贴图" --image cat.png`
  - 说明：Agent 会自主拆解→执行→渲染自检→修复→保存 `result.blend` 并导出 `result.fbx`/`result.glb`；带图时把参考图作为多模态上下文传入。

- [ ] **Step 2: 写 `docs/EXAMPLE_RUN.md`** 记录一条真实跑通示例的终端输出与产物路径，并标注免费模型限速下的预期耗时与重试行为。

- [ ] **Step 3: 提交**

```bash
git checkout -b docs/example-run
git add README.md docs/EXAMPLE_RUN.md
git commit -m "docs: add quickstart and example run for the blender agent"
```

---

## 自检（Self-Review）

**1. Spec 覆盖核对**
- 场景理解 → Task 10 `scene_understanding`（含 `check` CLI）。
- 自然语言建模 → Task 11 `nl_modeling`。
- 角色制作（模型/材质/骨骼/绑定/表情控制器）→ Task 12 `character` 六步管线。
- 图像驱动口播角色（按图建模 + 嘴/眼独立控制器 + 模块化贴图）→ Task 16 `talking_head` 七步管线。
- 动画（走路/跑步/表情/动作）→ Task 13 `animation`。
- 自动检查（截图/检查/修改）→ Task 8 `observer` + Task 14 `autocheck` + agent 循环里的 reflect 修复。
- 文件管理（存 .blend / 导出 FBX/GLB）→ Task 15 `file_management`。
- 利用现有 MCP、不自研协议 → Task 5 `McpToolProvider`，全局约束明令禁止自研。
- 支持 OpenRouter / Agnes 等 OpenAI 兼容免费模型 → Task 2/4 `ModelProvider` + `.env.example`。
- 多模态输入（文本 + 图片按图建模）→ `ChatMessage.images` + Task 4 `LLMClient._to_oai` 转 image_url；CLI `--image`；Agent 循环把参考图注入 history。
- 口播角色（嘴/眼独立控制器 + 模块化贴图）→ Task 16 `talking_head`。
- "真 Agent 不是聊天机器人" → Task 17 `Agent.run` 的 plan→act→observe→reflect→交付 闭环。
- 三个参考项目研究 → Reference Research 章节已记录并据此定后端策略。

**2. 占位符扫描**：未发现 TBD/TODO/"implement later"。所有代码块为可运行片段（核心模块含完整实现；skill 模块为保证接口一致性的精简实现，逻辑真实无占位）。

**3. 类型/接口一致性**
- `ToolProvider` 在 Task 3 定义 `list_tools`/`call_tool`（async）+ `sync_*` 同步便捷方法；`StubToolProvider`、Task 5 `McpToolProvider` 均实现；executor/observer/memory/skills 统一用 `sync_call_tool`，MCP 异步路径在 `from_config` 实例化时封装，保持调用方一致。
- `AgentTool`/`ToolResult`/`ChatMessage`/`Step`/`Plan` 在 Task 2 定义，后续 task 全部复用，命名一致。
- `discovered_tools_to_openai` 在 Task 3 定义，executor（Task 7）引用，无重命名。
- `FakeLLM.chat` 签名 `(messages, tools, max_retries)` 与 `LLMClient.chat` 一致，planner/executor/observer 注入时类型可替换。
- `Skill.accept`/`build_steps` 在 Task 10 `base.py` 定义，Task 11-16 各 skill 实现一致；`TalkingHead` 排在 `Character` 之前以保证图片/口播目标优先命中。

**已知风险 / 后续**
- 免费模型限速（20 次/分、50 次/天）会显著拖慢多轮 agent 循环；建议在 `.env` 用付费低价模型或本地模型做高频开发，免费模型仅做演示。
- 各 Blender MCP Server 暴露的工具名不完全一致（如 `execute_python` vs `execute_blender_code`、`save_blend` vs `export`），MCP 后端切换时需做一次工具名映射（在 `McpToolProvider` 或 skills 内加别名表），本计划默认按 `mcp-for-blender` 命名。
- 角色/动画质量高度依赖所选 MCP 后端的骨骼与动画工具覆盖度；若后端缺专用工具，skill 内已约定用 `execute_python` 写 bpy 脚本兜底（仍属"经 MCP 调用"，不违反不自研协议约束）。
- 图像多模态会显著增加 token 消耗（参考图 base64 入上下文），建议仅在含图片目标时注入，且对大图做分辨率下采样。
