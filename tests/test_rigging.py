"""通用绑定层测试：任意网格 → 口播骨架（下颌/眼球/眨眼）。"""
import ast

from blender_agent.builders.rig import rig_script


def test_rig_script_is_valid_python():
    code = rig_script()
    ast.parse(code)


def test_rig_script_targets_any_mesh():
    code = rig_script()
    # 不绑定具体名字：按选中/全部网格自动挑目标
    assert "TALKING_RIG_OK" in code
    assert "Jaw" in code and "Eye_L" in code and "Eye_R" in code
    assert "Blink" in code


def test_rig_script_accepts_target_name():
    code = rig_script("CatMesh")
    assert "CatMesh" in code
    ast.parse(code)


def test_rig_script_has_auto_weights_and_export_friendly_names():
    code = rig_script("CatMesh")
    assert "ARMATURE_AUTO" in code  # 自动权重
    assert "TalkingRig" in code
