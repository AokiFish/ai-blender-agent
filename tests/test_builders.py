from blender_agent.builders import match_builder
from blender_agent.builders.cat import SCRIPT, build_script


def test_matches_cat_goal():
    b = match_builder("参考这张猫咪图片做口播角色")
    assert b is not None
    name, make = b
    assert name == "cat"
    script = make(None)
    # 脚本必须包含关键构建步骤，避免空壳注册
    for token in ["Cat_Head", "Cat_Eye_", "MouthOpen", "Blink", "Cat_Armature", "BUILD_OK"]:
        assert token in script


def test_no_match_for_unrelated_goal():
    assert match_builder("创建一个红色立方体") is None


def test_params_line_is_valid_python():
    """regression: json.dumps 会生成 true/false，Blender 执行时报 NameError。"""
    s = build_script({"stripes": False, "whiskers": True})
    line = next(ln for ln in s.splitlines() if ln.startswith("PARAMS = "))
    ns = {}
    exec(line, ns)  # 必须能作为 Python 字面量求值
    assert ns["PARAMS"]["stripes"] is False
    assert ns["PARAMS"]["whiskers"] is True


def test_default_script_tokens():
    for token in ["Cat_Head", "MouthOpen", "Blink", "BUILD_OK"]:
        assert token in SCRIPT


def test_build_script_injects_params():
    s = build_script({"fur": "#123456", "stripes": False, "bow": False})
    assert '"fur": "#123456"' in s
    # 必须是 Python 布尔字面量，否则脚本执行时 NameError: name 'true' is not defined
    assert '"stripes": False' in s and "true" not in s.split("def hx")[0]


def test_build_script_unknown_keys_ignored():
    s = build_script({"nonsense": 1, "fur": "#abcdef"})
    assert '"fur": "#abcdef"' in s and "nonsense" not in s


def test_build_script_without_params_equals_script():
    assert build_script() == SCRIPT
