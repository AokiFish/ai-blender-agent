from blender_agent.skills.file_management import FileManagement


def test_build_steps_includes_save_and_export():
    steps = FileManagement(None).build_steps("导出 fbx glb",
                                            {"workspace": ".", "base_name": "result"})
    goals = " ".join(s.goal for s in steps)
    assert ".blend" in goals
    assert "execute_blender_code" in goals  # 真实环境用它做保存/导出
    assert any("fbx" in s.goal.lower() for s in steps)
    assert any("glb" in s.goal.lower() for s in steps)


def test_expected_paths():
    paths = FileManagement.expected_paths("导出 fbx glb", ".", "result")
    assert paths[0].endswith(".blend")
    assert any(p.endswith(".fbx") for p in paths)
    assert any(p.endswith(".glb") for p in paths)
