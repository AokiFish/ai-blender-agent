from blender_agent.core.observer import Observer
from blender_agent.core.tool_provider import StubToolProvider


def test_observer_runs_deterministic_check():
    stub = StubToolProvider({"execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0"})
    obs = Observer(stub, vlm=None)
    rep = obs.check("建一个 cube", None)
    assert rep["passed"] is True and rep["issues"] == []


def test_observer_flags_issue():
    stub = StubToolProvider({"execute_python": lambda a: "non_manifold_edges:3\nzero_area_faces:1"})
    obs = Observer(stub, vlm=None)
    rep = obs.check("建一个 cube", None)
    assert rep["passed"] is False and len(rep["issues"]) == 2
