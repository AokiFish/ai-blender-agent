"""Agent 集成：有参考图时先 VLM 提取特征，再注入确定性构建器。"""
import json
import os

from blender_agent.core.agent import Agent
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage


def _stub_with_recorder(calls: list):
    def code_handler(args):
        calls.append(args.get("code", ""))
        return "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0"

    return StubToolProvider({
        "execute_blender_code": code_handler,
        "look": lambda a: "viewport screenshot",
    })


def _run_with_feature_json(tmp_path, feature_reply: str):
    from blender_agent.config import load_config
    recorded = []
    provider = _stub_with_recorder(recorded)
    llm = FakeLLM([ChatMessage(role="assistant", content=feature_reply)])
    cfg = load_config()
    agent = Agent(llm, provider, cfg)
    agent.cfg.workspace = str(tmp_path)
    out = agent.run("参考图片制作猫咪口播角色", image=b"fakejpeg")
    return agent, out, recorded, tmp_path


def test_agent_extracts_features_and_injects(tmp_path):
    reply = ('{"fur": "#aa3344", "muzzle": "#ffffff", "inner_ear": "#ff9999", '
             '"nose": "#ffcccc", "iris": "#00ff00", "collar": "#ff0000", '
             '"stripes": false, "collar_on": true, "bow": true, "whiskers": true}')
    _, out, recorded, ws = _run_with_feature_json(tmp_path, reply)

    # features.json 落盘
    with open(os.path.join(ws, "features.json"), encoding="utf-8") as f:
        feats = json.load(f)
    assert feats["fur"] == "#aa3344" and feats["stripes"] is False

    # 注入构建器的脚本包含提取到的颜色
    assert any('"fur": "#aa3344"' in c for c in recorded)


def test_builder_output_not_modified_by_llm(tmp_path):
    """构建器产出后不允许 LLM 再执行改写脚本（实测会放大配饰/挪相机）。"""
    reply = ('{"fur": "#aa3344", "stripes": false}')
    _, _, recorded, _ = _run_with_feature_json(tmp_path, reply)
    assert len(recorded) == 1, f"构建器之后不应再有脚本执行，实际 {len(recorded)} 次"


def test_agent_without_image_uses_default_params(tmp_path):
    recorded = []
    provider = _stub_with_recorder(recorded)
    llm = FakeLLM([])
    from blender_agent.config import load_config
    cfg = load_config()
    agent = Agent(llm, provider, cfg)
    agent.cfg.workspace = str(tmp_path)
    agent.run("做一只猫咪口播角色")
    assert recorded, "builder 分支应执行构建脚本"
    assert '"fur": "#eb8029"' in recorded[0]  # 默认特征
    assert not os.path.exists(os.path.join(tmp_path, "features.json"))


def test_agent_feature_extraction_failure_still_builds(tmp_path):
    # LLM 挂掉 → 回退默认特征，任务不崩
    class BoomOnceLLM:
        """第一次调用（特征提取）抛错，之后返回空消息。"""

        def __init__(self):
            self.n = 0

        def chat(self, *a, **k):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("llm down")
            return ChatMessage(role="assistant", content="")

    recorded = []
    provider = _stub_with_recorder(recorded)
    from blender_agent.config import load_config
    cfg = load_config()
    agent = Agent(BoomOnceLLM(), provider, cfg)
    agent.cfg.workspace = str(tmp_path)
    out = agent.run("猫咪口播角色", image=b"x")
    assert '"fur": "#eb8029"' in recorded[0]
