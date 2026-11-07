"""视图生成层测试：agnes image i2i 多视角生成。"""
import os

import pytest

from blender_agent.core.viewgen import VIEW_PROMPTS, generate_views


class FakeImageAPI:
    """模拟 OpenAI 兼容的 /images/generations：返回 URL，下载即固定字节。"""

    def __init__(self, fail_views=()):
        self.calls = []
        self.fail_views = set(fail_views)

    def post_image(self, payload):
        self.calls.append(payload)
        prompt = payload["prompt"]
        view = next((v for v in VIEW_PROMPTS if VIEW_PROMPTS[v] == prompt), "unknown")
        if view in self.fail_views:
            raise RuntimeError("api down")
        return f"https://cdn.example/{view}.png"

    def download(self, url):
        return b"PNG:" + url.encode()


def test_generate_views_writes_files(tmp_path):
    api = FakeImageAPI()
    paths = generate_views(b"\x89PNGref", str(tmp_path), api=api)
    assert len(paths) == len(VIEW_PROMPTS)
    for p in paths:
        assert os.path.isfile(p)
        assert open(p, "rb").read().startswith(b"PNG:")
    # 每次请求都带参考图（i2i）
    assert all(c["image"].startswith("data:image/jpeg;base64,") for c in api.calls)


def test_generate_views_survives_partial_failure(tmp_path):
    api = FakeImageAPI(fail_views={"side"})
    paths = generate_views(b"ref", str(tmp_path), api=api)
    assert len(paths) == len(VIEW_PROMPTS) - 1
    assert not any("side" in p for p in paths)


def test_generate_views_all_fail_returns_empty(tmp_path):
    api = FakeImageAPI(fail_views=set(VIEW_PROMPTS))
    assert generate_views(b"ref", str(tmp_path), api=api) == []


def test_view_prompts_are_english_and_plain():
    for v, p in VIEW_PROMPTS.items():
        assert v in p or v.replace("_", " ") in p or v.replace("_", "-") in p
        assert p.isascii()
        assert "white background" in p
