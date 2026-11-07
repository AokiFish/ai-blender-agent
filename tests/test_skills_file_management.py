from blender_agent.skills.file_management import FileManagement
from blender_agent.core.tool_provider import StubToolProvider


def test_file_management_save_and_export():
    stub = StubToolProvider({
        "save_blend": lambda a: f"saved {a.get('path')}",
        "export_fbx": lambda a: f"exported {a.get('path')}",
        "export_glb": lambda a: f"exported {a.get('path')}",
    })
    out = FileManagement(stub).run("保存工程并导出 fbx 和 glb", ".", "result")
    assert any(d.endswith(".blend") for d in out["deliverables"])
    assert any(d.endswith(".fbx") for d in out["deliverables"])
    assert any(d.endswith(".glb") for d in out["deliverables"])
