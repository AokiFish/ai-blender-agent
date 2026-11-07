"""跨运行经验沉淀：VIGA 的循环只在单次运行内自我纠正，
这一层把"什么问题 → 怎么修好"持久化，让后续 run 起点更高 —— 真正的进化层。
"""
import json
import os


class Lessons:
    def __init__(self, path: str | None = None, cap: int = 30):
        self.path = path
        self.cap = cap
        self.items: list[dict] = []

    def load(self) -> "Lessons":
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.items = json.load(f) or []
            except (json.JSONDecodeError, OSError):
                self.items = []
        return self

    def save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, ensure_ascii=False, indent=2)

    def add(self, problem: str, fix: str) -> None:
        problem = (problem or "").strip()
        fix = (fix or "").strip()
        if not problem or not fix:
            return
        for it in self.items:
            if it["problem"] == problem:
                it["count"] = it.get("count", 1) + 1
                if fix != it["fix"]:
                    it["fix"] = fix
                break
        else:
            self.items.append({"problem": problem, "fix": fix, "count": 1})
        # 高频教训优先保留；同频按时间倒序（新的在前）
        self.items.sort(key=lambda x: -x.get("count", 1))
        self.items = self.items[: self.cap]
        self.save()

    def add_from_report(self, report, applied_fixes: dict[str, str]) -> None:
        """把一轮 verify→patch 的因果沉淀下来：issue.feature → 实际生效的修法。"""
        for issue in report.issues:
            feat = issue.get("feature", "")
            fix = applied_fixes.get(feat) or issue.get("fix_hint", "")
            self.add(feat, fix)


def format_lessons(lessons: Lessons, top: int = 8) -> str:
    lines = [f"- {it['problem']}（出现过 {it.get('count', 1)} 次）→ {it['fix']}"
             for it in lessons.items[:top]]
    return "\n".join(lines) if lines else "（暂无）"
