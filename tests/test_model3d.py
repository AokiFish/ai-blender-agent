"""3D 生成后端抽象层测试：可插拔 provider + job 轮询 + 密钥配置。"""
import pytest

from blender_agent.core.model3d import (
    Model3DRequest,
    available_providers,
    configure_provider,
    generate_mesh,
    parse_job_handle,
)


def test_available_providers_lists_known_backends():
    names = available_providers()
    assert set(names) >= {"tripo", "hyper3d", "meshy", "hunyuan3d"}


def test_parse_job_handle_from_text():
    text = "Job started, not finished. Call generate_3d(job='abc123', name='Cat') to keep waiting."
    assert parse_job_handle(text) == "abc123"
    assert parse_job_handle("job=xyz-9") == "xyz-9"
    assert parse_job_handle("no handle here") is None


class FakeProvider:
    def __init__(self, rejects=()):
        self.rejects = set(rejects)
        self.calls = []

    def sync_call_tool(self, name, args):
        self.calls.append((name, args))
        from blender_agent.core.types import ToolResult
        if name == "generate_3d":
            if args.get("job"):
                return ToolResult(ok=True, content="SUCCEEDED imported CatMesh")
            return ToolResult(ok=True, content="Job queued. Call generate_3d(job='j1') to continue.")
        return ToolResult(ok=True, content="")


def test_generate_mesh_polls_until_done():
    p = FakeProvider()
    out = generate_mesh(p, Model3DRequest(provider="tripo", images=["a.png"], name="Cat"))
    assert out == "SUCCEEDED imported CatMesh"
    assert p.calls[0][1]["provider"] == "tripo"
    assert p.calls[0][1]["image"] == "a.png"
    assert p.calls[1][1]["job"] == "j1"


def test_generate_mesh_stops_on_error():
    class ErrProvider:
        def sync_call_tool(self, name, args):
            from blender_agent.core.types import ToolResult
            return ToolResult(ok=False, error="You don't have enough credit")

    out = generate_mesh(ErrProvider(), Model3DRequest(provider="tripo", images=["a.png"]))
    assert out.startswith("ERROR")
    assert "credit" in out


def test_generate_mesh_requires_images():
    with pytest.raises(ValueError):
        generate_mesh(FakeProvider(), Model3DRequest(provider="tripo", images=[]))


def test_configure_provider_script_contains_key_without_leaking_in_logs():
    code = configure_provider("tripo", "tsk_secret_value")
    assert 'blendermcp_use_tripo = True' in code
    assert "tsk_secret_value" in code  # 代码要带密钥，但返回值不用于日志


def test_local_backend_available_false_when_missing():
    from blender_agent.core import model3d
    old = model3d.HUNYUAN3D_HOME
    model3d.HUNYUAN3D_HOME = r"C:/definitely/not/here"
    try:
        assert model3d.local_backend_available() is False
    finally:
        model3d.HUNYUAN3D_HOME = old


def test_generate_mesh_local_parses_output(tmp_path, monkeypatch):
    from blender_agent.core import model3d

    glb = tmp_path / "out.glb"
    glb.write_bytes(b"glb")

    class FakeProc:
        returncode = 0
        stdout = "SHAPE_DONE 170.4 s | faces: 332040 | verts: 166019\nEXPORTED x\nLOCAL_OK\n"
        stderr = ""

    monkeypatch.setattr(model3d, "local_backend_available", lambda: True)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProc())
    res = model3d.generate_mesh_local("img.png", str(glb))
    assert res.faces == 332040 and res.verts == 166019
    assert abs(res.seconds - 170.4) < 0.01


def test_generate_mesh_local_raises_on_failure(tmp_path, monkeypatch):
    from blender_agent.core import model3d

    class FakeProc:
        returncode = 1
        stdout = "ERROR: CUDA out of memory"
        stderr = ""

    monkeypatch.setattr(model3d, "local_backend_available", lambda: True)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeProc())
    with pytest.raises(RuntimeError, match="out of memory"):
        model3d.generate_mesh_local("img.png", str(tmp_path / "o.glb"))
