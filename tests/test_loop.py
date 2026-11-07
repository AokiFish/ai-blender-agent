"""多视角诊断渲染 + write-run-compare-revise 循环的测试。"""
import os
import json

from blender_agent.core.loop import ReviseLoop, render_views, build_patch_prompt
from blender_agent.core.types import Step, ToolResult
from blender_agent.core.lessons import Lessons


PNG = b"\x89PNG fake"


class StubProvider:
    """最小 stub：execute_blender_code 返回成功；文件系统读写照常。"""
    def sync_call_tool(self, name, args):
        assert name == "execute_blender_code"
        return ToolResult(ok=True, content="RENDER_VIEWS_OK")

    def sync_list_tools(self):
        return []


class SeqLLM:
    """按序回复：奇数次=verifier JSON，偶数次=patch 代码。"""
    def __init__(self, verifier_scores):
        self.scores = list(verifier_scores)
        self.patch_prompts = []

    def chat(self, messages, tools=None, response_format=None, **kw):
        content = messages[0].content
        if "只输出 JSON" in content:  # verifier 提示词特征
            s = self.scores.pop(0)
            cont = s < 8
            return type("R", (), {"content": json.dumps({
                "score": s, "should_continue": cont,
                "summary": f"score {s}",
                "issues": [] if s >= 8 else [
                    {"feature": "fur_color", "expected": "x", "actual": "y",
                     "severity": "medium", "fix_hint": "调色"}]})})()
        self.patch_prompts.append(content)
        return type("R", (), {"content": "import bpy\n# patch"})()


def _fake_views(provider, ws, ref_bytes=None):
    """测试替身：写出假 PNG 返回路径。"""
    d = os.path.join(ws, "diag")
    os.makedirs(d, exist_ok=True)
    paths = []
    for name in ("front", "side45", "side90"):
        p = os.path.join(d, f"{name}.png")
        with open(p, "wb") as f:
            f.write(PNG)
        paths.append(p)
    return paths


def test_loop_converges_and_writes_trajectory(tmp_path):
    ws = str(tmp_path)
    lessons = Lessons(path=os.path.join(ws, "lessons.json"))
    loop = ReviseLoop(StubProvider(), tmp_path, lessons=lessons,
                      max_rounds=4, views_fn=_fake_views)
    llm = SeqLLM(verifier_scores=[6.0, 8.5])
    loop.llm = llm
    out = loop.run(ref_image=PNG)
    assert out["final_score"] == 8.5
    assert len(out["scores"]) == 2
    # 轨迹落盘
    tj = out["trajectory"]
    assert os.path.isdir(os.path.join(tj, "renders"))
    assert os.path.isfile(os.path.join(tj, "scores.json"))
    assert os.path.isfile(os.path.join(tj, "verifier", "round1.json"))
    assert os.path.isfile(os.path.join(tj, "codes", "round1.py"))


def test_loop_persists_lessons_across_runs(tmp_path):
    ws = str(tmp_path)
    lpath = os.path.join(ws, "lessons.json")
    loop = ReviseLoop(StubProvider(), ws, lessons=Lessons(path=lpath),
                      max_rounds=3, views_fn=_fake_views)
    loop.llm = SeqLLM(verifier_scores=[5.0, 5.5, 6.0])
    loop.run(ref_image=PNG)
    ls = Lessons(path=lpath).load()
    assert any(i["problem"] == "fur_color" for i in ls.items)


def test_patch_prompt_contains_constraints_memory_lessons(tmp_path):
    prompt = build_patch_prompt(
        issues=[{"feature": "framing", "actual": "角色过小"}],
        memory="第1轮评分5.0",
        lessons="- fur_color（出现过 2 次）→ 调色",
        plan_summary="确定性构建器 cat 已产出 38 部件")
    assert "材质" in prompt and "拓扑" in prompt  # 允许/禁止边界
    assert "第1轮评分5.0" in prompt and "fur_color" in prompt
    assert "38 部件" in prompt


def test_render_views_returns_paths(tmp_path):
    class P:
        def sync_call_tool(self, name, args):
            return ToolResult(ok=True, content="RENDER_VIEWS_OK front=/a.png")
    paths = render_views(P(), str(tmp_path))
    assert len(paths) == 3


def test_bad_verifier_output_stops_loop_without_patch(tmp_path):
    """Verifier 输出不可解析 → 不打补丁白烧一轮，直接止损。"""
    loop = ReviseLoop(StubProvider(), str(tmp_path),
                      lessons=Lessons(path=os.path.join(str(tmp_path), "l.json")),
                      max_rounds=3, views_fn=_fake_views)
    llm = SeqLLM(verifier_scores=[])  # 走 FakeLLM 式空回复
    llm.chat = lambda messages, **kw: type("R", (), {"content": "这不是 JSON"})()
    loop.llm = llm
    out = loop.run(ref_image=PNG)
    assert out["scores"] == [] and out["verified"] is False
    assert not os.path.exists(os.path.join(out["trajectory"], "codes", "round1.py"))
