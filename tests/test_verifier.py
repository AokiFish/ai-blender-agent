"""Verifier 结构化反馈 + lessons 跨运行沉淀 的测试。"""
from blender_agent.core.verifier import VerifierReport, verify
from blender_agent.core.lessons import Lessons, format_lessons


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools=None, response_format=None, **kw):
        self.calls.append(messages)
        return type("R", (), {"content": self.replies.pop(0)})()


def test_report_from_json_strips_fence():
    text = '```json\n{"score": 6.5, "should_continue": true, "summary": "颜色偏灰",\n "issues": [{"feature": "fur_color", "expected": "#e8a87c", "actual": "灰橘", "severity": "medium", "fix_hint": "调 Base Color"}]}\n```'
    r = VerifierReport.from_json(text)
    assert r.score == 6.5 and r.should_continue is True
    assert r.issues[0]["feature"] == "fur_color"


def test_report_from_json_garbage_falls_back():
    r = VerifierReport.from_json("模型胡言乱语没有 JSON")
    assert r.score == 0.0 and r.should_continue is True  # 保守：继续修
    assert "parse_error" in r.issues[0]["feature"]


def test_verify_builds_prompt_with_memory_and_lessons():
    llm = FakeLLM(['{"score": 9, "should_continue": false, "issues": [], "summary": "达标"}'])
    report = verify(llm, b"ref", b"render", memory="第1轮：调了毛色", lessons="教训：不要动相机")
    assert report.score == 9
    content = llm.calls[0][0].content
    assert "第1轮：调了毛色" in content and "教训：不要动相机" in content
    assert llm.calls[0][0].images == [b"ref", b"render"]


def test_verify_without_reference_image():
    llm = FakeLLM(['{"score": 5, "should_continue": true, "issues": [], "summary": "x"}'])
    verify(llm, None, b"render", memory="", lessons="")
    assert llm.calls[0][0].images == [b"render"]


# ---------- lessons ----------
def test_lessons_add_dedup_and_cap():
    ls = Lessons(cap=3)
    ls.add("相机被挪动", "构建器产物禁止改相机")
    ls.add("相机被挪动", "构建器产物禁止改相机")  # 去重，count+1
    ls.add("毛色偏灰", "按 features.json 的 hex 校验材质")
    ls.add("嘴不可见", "加大 MouthOpen shape key 幅度")
    ls.add("脖子太长", "无")
    assert len(ls.items) == 3  # cap=3，最旧的"相机"仍在（count 高优先保留）or FIFO — 由实现定义
    assert isinstance(format_lessons(ls), str)


def test_lessons_roundtrip(tmp_path):
    path = tmp_path / "lessons.json"
    ls = Lessons(path=path)
    ls.add("嘴不可见", "加大 MouthOpen 幅度")
    ls2 = Lessons(path=path)
    ls2.load()
    assert ls2.items[0]["problem"] == "嘴不可见"


def test_lessons_bad_file_tolerated(tmp_path):
    path = tmp_path / "lessons.json"
    path.write_text("not json", encoding="utf-8")
    ls = Lessons(path=path)
    ls.load()
    assert ls.items == []
