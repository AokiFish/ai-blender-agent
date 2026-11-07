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
