from blender_agent.builders import match_builder


def test_matches_cat_goal():
    b = match_builder("参考这张猫咪图片做口播角色")
    assert b is not None
    name, script = b
    assert name == "cat"
    # 脚本必须包含关键构建步骤，避免空壳注册
    for token in ["Cat_Head", "Cat_Eye_", "MouthOpen", "Blink", "Cat_Armature", "BUILD_OK"]:
        assert token in script


def test_no_match_for_unrelated_goal():
    assert match_builder("创建一个红色立方体") is None
