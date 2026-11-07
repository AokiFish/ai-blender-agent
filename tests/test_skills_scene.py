from blender_agent.skills.scene_understanding import SceneUnderstanding
from blender_agent.core.tool_provider import StubToolProvider


def test_scene_report_calls_get_scene_info():
    seen = {}
    stub = StubToolProvider({"get_scene_info": lambda a: seen.update(a) or "Objects:[Cube]"})
    rep = SceneUnderstanding(stub).report()
    assert "Cube" in rep and seen == {}
