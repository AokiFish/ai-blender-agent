from blender_agent.core.tool_provider import ToolProvider, resolve_code_tool
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
            # mcp-for-blender 没有独立 save 工具，用 execute_blender_code 保存
            tool = resolve_code_tool(provider)
            provider.sync_call_tool(tool, {
                "code": f"import bpy\nbpy.ops.wm.save_as_mainfile(filepath={path!r})"})
            return True
        return False

    def summary(self) -> str:
        return "\n".join(f"[{'OK' if e['ok'] else 'FAIL'}] {e['goal']}" for e in self.log)
