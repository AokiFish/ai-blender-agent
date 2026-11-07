import pytest


@pytest.fixture
def stub_provider():
    from blender_agent.core.tool_provider import StubToolProvider
    return StubToolProvider({
        "get_scene_info": lambda a: "Objects: [Cube]",
        "create_primitive": lambda a: f"created {a.get('type', 'cube')}",
        "set_material": lambda a: "material set",
        "save_blend": lambda a: f"saved {a.get('path')}",
        "export_fbx": lambda a: f"exported {a.get('path')}",
        "execute_python": lambda a: "non_manifold_edges:0\nzero_area_faces:0\nmeshes_missing_material:0",
    })
