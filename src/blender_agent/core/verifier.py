"""结构化 Verifier：对比参考图与渲染图，输出可执行的 JSON 修订反馈。

借鉴 VIGA 的 Verifier 角色：不做模糊的 PASS/FAIL，
而是逐特征列出 expected/actual/severity/fix_hint，
让 Generator 能针对性打补丁而不是重做。
"""
import json
import re
from dataclasses import dataclass, field

VERIFY_PROMPT = """你是 3D 场景质检员（Verifier）。第一张是参考图，第二张是当前 Blender 渲染。
逐项对比并只输出 JSON（不要其他文字）：
{{
  "score": 0-10 的相似度,
  "should_continue": true/false（低于 8 分继续修）,
  "summary": "一句话总评",
  "issues": [
    {{"feature": "特征名如 fur_color/ear_shape/pose/framing",
      "expected": "参考图中的样子",
      "actual": "渲染中的样子",
      "severity": "high|medium|low",
      "fix_hint": "一句话修法，只允许改材质颜色/物体变换/灯光/相机构图"}}
  ]
}}
最多列 5 个问题，按 severity 排序。若已高度相似则 issues 为空。"""


@dataclass
class VerifierReport:
    score: float = 0.0
    should_continue: bool = True
    summary: str = ""
    issues: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, text: str) -> "VerifierReport":
        """容错解析：剥 ``` 围栏、截取首个 {...} 块；失败给保守默认（继续修）。"""
        if not text:
            return cls(issues=[{"feature": "parse_error", "severity": "medium",
                                "fix_hint": "Verifier 无输出，人工检查渲染"}])
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return cls.from_json("")
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return cls.from_json("")
        issues = d.get("issues") or []
        return cls(
            score=float(d.get("score", 0)),
            should_continue=bool(d.get("should_continue", True)),
            summary=str(d.get("summary", "")),
            issues=issues[:5] if isinstance(issues, list) else [],
        )

    def to_memory(self, round_no: int) -> str:
        """压成一行摘要，供下一轮注入上下文（渲染历史）。"""
        tops = "; ".join(f"{i.get('feature')}:{i.get('actual')}→{i.get('fix_hint')}"
                         for i in self.issues[:3])
        return f"第{round_no}轮评分{self.score}，{self.summary}。问题：{tops or '无'}"


def verify(llm, ref_image: bytes | None, render_image: bytes,
           memory: str = "", lessons: str = "") -> VerifierReport:
    """渲染图（必选）与参考图（可选）喂给 VLM，拿结构化报告。

    agnes 等模型偶尔返回空内容：先请求 JSON 模式，不支持则退普通调用；
    解析失败再补一次"只输出 JSON"的纠错。
    """
    from blender_agent.core.types import ChatMessage
    ctx = ""
    if memory:
        ctx += f"\n\n【历史修订记录】\n{memory}"
    if lessons:
        ctx += f"\n\n【往期教训（优先避免）】\n{lessons}"
    images = ([ref_image] if ref_image else []) + [render_image]
    prompt = VERIFY_PROMPT + ctx

    def _ask(text: str) -> str:
        msg = ChatMessage(role="user", content=text, images=images)
        try:
            return llm.chat([msg], response_format={"type": "json_object"}).content or ""
        except Exception:  # 服务商不支持 json 模式
            return llm.chat([msg]).content or ""

    report = VerifierReport.from_json(_ask(prompt))
    if is_parse_error(report):
        report = VerifierReport.from_json(
            _ask(prompt + "\n\n上次输出无法解析。只输出 JSON 对象，不要任何解释。"))
    return report


def is_parse_error(r: VerifierReport) -> bool:
    return any(i.get("feature") == "parse_error" for i in r.issues)
