from blender_agent.core.features import CatFeatures, extract_features
from blender_agent.core.types import ChatMessage


class EchoLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, messages, tools=None, max_retries=3):
        self.calls.append(messages)
        return ChatMessage(role="assistant", content=self.reply)


def test_from_json_plain():
    f = CatFeatures.from_json('{"fur": "#e07820", "muzzle": "#ffffff", "stripes": false}')
    assert f.fur == "#e07820" and f.stripes is False


def test_from_json_with_code_fence():
    text = '```json\n{"fur": "#ff8800", "nose": "#ffaaaa", "collar_on": true}\n```'
    f = CatFeatures.from_json(text)
    assert f.fur == "#ff8800" and f.collar_on is True


def test_from_json_invalid_falls_back_to_defaults():
    f = CatFeatures.from_json("这不是 JSON")
    assert f == CatFeatures.DEFAULTS()


def test_from_json_bad_hex_uses_default_for_that_field():
    f = CatFeatures.from_json('{"fur": "orange", "iris": "#123456"}')
    assert f.fur == CatFeatures.DEFAULTS().fur
    assert f.iris == "#123456"


def test_to_params_has_all_colors():
    p = CatFeatures.DEFAULTS().to_params()
    for k in ["fur", "muzzle", "inner_ear", "nose", "iris", "collar"]:
        assert k in p
    for k in ["stripes", "collar_on", "bow", "whiskers"]:
        assert k in p


def test_extract_features_sends_image_and_parses():
    llm = EchoLLM('{"fur": "#e07820", "muzzle": "#fff8f0"}')
    f = extract_features(llm, b"fakepng")
    assert f.fur == "#e07820"
    assert llm.calls[0][0].images == [b"fakepng"]


def test_extract_features_llm_error_falls_back():
    class Boom:
        def chat(self, *a, **k):
            raise RuntimeError("boom")

    assert extract_features(Boom(), b"x") == CatFeatures.DEFAULTS()
