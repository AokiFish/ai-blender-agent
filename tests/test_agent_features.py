"""Agent 集成：有参考图时先 VLM 提取特征，再注入确定性构建器。"""
import json
import os

from blender_agent.core.agent import Agent
from blender_agent.core.llm import FakeLLM
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import ChatMessage


def _stub_with_recorder(calls: list, ws_holder: dict | None = None):
    def code_handler(args):
        code = args.get("code", "")
        calls.append(code)
        if "DIAG_VIEW" in code and ws_holder and ws_holder.get("ws"):
            # 模拟诊断渲染：写出假 PNG，让修订循环能拿到图
            d = os.path.join(ws_holder["ws"], "diag")
            os.makedirs(d, exist_ok=True)
            for n in ("front", "side45", "side90"):
                with open(os.path.join(d, f"{n}.png"), "wb") as f:
                    f.write(b"\x89PNG fake")
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


def test_builder_followed_by_verifier_loop_only(tmp_path):
    """构建器产出后不走 skill 计划步骤；接下来只应是诊断渲染 + verifier 驱动修订。"""
    verifier_json = ('{"score": 9, "should_continue": false, "summary": "达标", "issues": []}')
    reply = ('{"fur": "#aa3344", "stripes": false}')
    recorded = []
    ws_holder = {"ws": str(tmp_path)}
    provider = _stub_with_recorder(recorded, ws_holder)
    llm = FakeLLM([ChatMessage(role="assistant", content=reply),
                   ChatMessage(role="assistant", content=verifier_json)])
    from blender_agent.config import load_config
    cfg = load_config()
    agent = Agent(llm, provider, cfg)
    agent.cfg.workspace = str(tmp_path)
    agent.run("参考图片制作猫咪口播角色", image=b"fakejpeg")
    assert len(recorded) == 3  # 构建脚本 + 诊断渲染 + 确定性交付脚本（无 LLM 补丁）
    assert "DIAG_VIEW" in recorded[1]
    assert "DELIVER_OK" in recorded[2]


def test_loop_writes_trajectory_and_lessons(tmp_path):
    verifier_json = ('{"score": 6, "should_continue": true, "summary": "毛色偏灰", '
                     '"issues": [{"feature": "fur_color", "expected": "橘", "actual": "灰", '
                     '"severity": "medium", "fix_hint": "调 Base Color"}]}')
    reply = '{"fur": "#aa3344", "stripes": false}'
    recorded = []
    ws_holder = {"ws": str(tmp_path)}
    provider = _stub_with_recorder(recorded, ws_holder)
    llm = FakeLLM([ChatMessage(role="assistant", content=reply),
                   ChatMessage(role="assistant", content=verifier_json),
                   ChatMessage(role="assistant", content=verifier_json)])
    from blender_agent.config import load_config
    cfg = load_config()
    agent = Agent(llm, provider, cfg)
    agent.cfg.workspace = str(tmp_path)
    agent.run("参考图片制作猫咪口播角色", image=b"x")
    ls = json.load(open(os.path.join(tmp_path, "lessons.json"), encoding="utf-8"))
    assert any(i["problem"] == "fur_color" for i in ls)
    traj = os.path.join(tmp_path, "trajectory")
    hits = [os.path.join(r, fn) for r, _, fs in os.walk(traj)
            for fn in fs if fn == "scores.json"]
    assert hits, "trajectory 下应有 scores.json"


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
