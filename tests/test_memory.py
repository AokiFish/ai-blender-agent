from blender_agent.core.memory import Memory
from blender_agent.core.tool_provider import StubToolProvider
from blender_agent.core.types import Step, ToolResult


def test_checkpoint_called_every_n_steps():
    saves = []
    stub = StubToolProvider({"save_blend": lambda a: saves.append(a["path"])})
    mem = Memory(checkpoint_every=2)
    for i in range(4):
        mem.record(Step(index=i, goal=f"g{i}"), ToolResult(ok=True))
        mem.maybe_checkpoint(stub, "/tmp/r.blend")
    assert len(saves) == 2  # 第2、第4步后各存一次
