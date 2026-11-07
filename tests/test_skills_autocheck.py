from blender_agent.skills.autocheck import AutoCheck
from blender_agent.core.observer import Observer
from blender_agent.core.tool_provider import StubToolProvider


def test_autocheck_reports_pass():
    stub = StubToolProvider({"execute_python": lambda a:
        "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0"})
    rep = AutoCheck(Observer(stub, None)).run("检查模型")
    assert rep["passed"] is True
