# VLM 参考图特征提取 → 参数化复刻猫咪 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 VLM 从参考图提取猫咪特征（颜色/斑纹/配饰/耳朵），注入确定性 builder 复刻角色，实现"按图复刻且可复现"。

**Architecture:** 新增 `core/features.py`（CatFeatures 数据类 + VLM JSON 提取 + 容错回退默认值）；cat.py 的 SCRIPT 改为 `build_script(params)` 模板（颜色/开关由 PARAMS 字典注入，几何骨架不变）；agent.py 在 builder 分支有图时先提取特征、存 features.json、再生成定制脚本。

**Tech Stack:** Python 3.13 venv、OpenAI 兼容多模态 LLM（agnes-2.5-flash）、bpy 脚本、pytest。

**Spec:** 用户需求——"试试你说的 VLM 从参考图提取特征，然后再制作"；现状痛点：builder 颜色硬编码，参考图信息完全没用上。

## Global Constraints

- 不编造工具名：只走 `execute_blender_code`（mcp-for-blender 真实工具）。
- LLM 返回 JSON 可能带 markdown 代码围栏，解析必须剥掉。
- 解析失败回退默认特征，不许让整次任务崩掉。
- 默认（无特征注入）生成的脚本必须与现状完全等价。
- 仓库在 main 直接提交（沙箱分支 bug 规避），Conventional Commits 英文 message。

---

### Task 1: CatFeatures 特征模型 + VLM 提取

**Files:**
- Create: `src/blender_agent/core/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Produces: `CatFeatures`（字段 fur/muzzle/inner_ear/nose/iris/collar 十六进制色，stripes/collar/bow/whiskers 布尔开关；`from_json(text)->CatFeatures`、`to_params()->dict`、`DEFAULTS`）；`extract_features(llm, image: bytes) -> CatFeatures`。

- [ ] **Step 1: 写失败测试**

```python
from blender_agent.core.features import CatFeatures, extract_features
from blender_agent.core.types import ChatMessage


class EchoLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, messages, tools=None, max_retries=3):
        self.calls.append(messages)
        return ChatMessage(role="assistant", content=self.reply)


def test_from_json_plain():
    f = CatFeatures.from_json('{"fur": "#e07820", "muzzle": "#ffffff", "stripes": false}')
    assert f.fur == "#e07820" and f.stripes is False


def test_from_json_with_code_fence():
    text = '```json\n{"fur": "#ff8800", "nose": "#ffaaaa", "collar": true}\n```'
    f = CatFeatures.from_json(text)
    assert f.fur == "#ff8800" and f.collar is True


def test_from_json_invalid_falls_back_to_defaults():
    f = CatFeatures.from_json("这不是 JSON")
    assert f == CatFeatures.DEFAULTS()


def test_to_params_has_all_colors():
    p = CatFeatures.DEFAULTS().to_params()
    for k in ["fur", "muzzle", "inner_ear", "nose", "iris", "collar"]:
        assert k in p


def test_extract_features_sends_image_and_parses():
    llm = EchoLLM('{"fur": "#e07820", "muzzle": "#fff8f0"}')
    f = extract_features(llm, b"fakepng")
    assert f.fur == "#e07820"
    assert llm.calls[0][0].images == [b"fakepng"]


def test_extract_features_llm_error_falls_back():
    class Boom:
        def chat(self, *a, **k):
            raise RuntimeError("boom")
    assert extract_features(Boom(), b"x") == CatFeatures.DEFAULTS()
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_features.py -v` → ImportError。

- [ ] **Step 3: 实现 features.py**

要点：`from_json` 先剥 ``` 围栏再 `json.loads`，逐字段容错（缺字段用默认），hex 校验 `#`+6位，非法值丢弃用默认。`extract_features` 提示词要求严格 JSON、列出全部字段含义，拿 reply 喂 `from_json`，任何异常返回 `DEFAULTS()`。

- [ ] **Step 4: 跑测试通过** — `pytest tests/test_features.py -v`。

- [ ] **Step 5: Commit** — `git commit -m "feat: VLM feature extraction from reference image"`。

### Task 2: cat.py 参数化（颜色/开关由 PARAMS 注入）

**Files:**
- Modify: `src/blender_agent/builders/cat.py`
- Test: `tests/test_builders.py`（追加用例）

**Interfaces:**
- Produces: `build_script(params: dict | None = None) -> str`；`SCRIPT = build_script()` 保留向后兼容。

- [ ] **Step 1: 写失败测试**

```python
from blender_agent.builders.cat import SCRIPT, build_script


def test_default_script_unchanged_tokens():
    for token in ["Cat_Head", "MouthOpen", "Blink", "BUILD_OK"]:
        assert token in SCRIPT


def test_build_script_injects_params():
    s = build_script({"fur": "#123456", "stripes": False, "bow": False})
    assert "#123456" in s
    assert '"fur": "#123456"' in s


def test_build_script_without_params_equals_script():
    assert build_script() == SCRIPT
```

- [ ] **Step 2: 跑测试确认失败**（build_script 不存在）。

- [ ] **Step 3: 改造 cat.py**

SCRIPT 头部注入 `PARAMS = {...}` 字典字面量（`json.dumps` 生成）；材质行改为 `hex2rgb(PARAMS["fur"])` 取色；stripes/collar/bow/whiskers 改为按 `PARAMS["stripes"]` 等布尔条件创建；其余几何/骨架/shape key 不动。模块级：`_BODY`（原脚本正文，其中 PARAMS 行用占位）+ `build_script(params=None)`：params 为 None 时用内置默认值渲染。

- [ ] **Step 4: 全量测试通过** — `pytest -q`。

- [ ] **Step 5: Commit** — `feat: parametric cat builder accepts feature params`。

### Task 3: agent.py 集成（有图先提取特征再构建）

**Files:**
- Modify: `src/blender_agent/core/agent.py`（builder 分支，约 91-105 行）
- Test: `tests/test_agent_features.py`

**Interfaces:**
- Consumes: Task 1 `extract_features`、Task 2 `build_script`。
- Produces: builder 分支有图时输出 `workspace/features.json`；`match_builder` 返回改为 `(name, build_script)`（registry 存工厂）。

- [ ] **Step 1: 写失败测试**

```python
from blender_agent.core.features import CatFeatures
# 用 Stub provider + FakeLLM：agent.run 带图时
# 1) features.json 写入 workspace 2) execute_blender_code 收到的 code 含 "#e07820"
```

（完整断言代码在实现时展开：FakeLLM 队列返回合法特征 JSON；执行后读 features.json 断言 fur；从 stub 收到的最后一条 execute_blender_code 参数里断言注入色值。）

- [ ] **Step 2: 失败 → 实现 → 通过 → commit** — `feat: agent extracts features from reference image before building`。

### Task 4: 真实联调（参考图复刻）

- [ ] 用 workspace 现存参考图 `cat_reference.jpg` 跑 CLI：`python -m blender_agent.cli run "参考图猫咪口播角色" --workspace workspace --image workspace/cat_reference.jpg`
- [ ] 检查 `workspace/features.json` 提取值合理；看渲染图判断是否贴近参考图（毛色/耳内/项圈等）
- [ ] 渲染图给用户看，必要时调提取提示词重跑
- [ ] Commit + push

## Self-Review

- 覆盖：提取(Task1)→注入(Task2)→编排(Task3)→实测(Task4)，闭环。
- 无占位符：Task 3 断言在实现时展开是唯一松点，实现以现有 Stub/FakeLLM 模式展开。
- 类型一致：`CatFeatures.to_params()` 的 key 与 cat.py 读取的 PARAMS key 一致（fur/muzzle/inner_ear/nose/iris/collar/stripes/collar_on/bow/whiskers——collar 色与开关分名字避免撞 key）。
