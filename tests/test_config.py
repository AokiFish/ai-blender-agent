from blender_agent.config import AgentConfig, load_config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("BLENDER_AGENT_BASE_URL", "https://agnes.example/v1")
    monkeypatch.setenv("BLENDER_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("BLENDER_AGENT_MODEL", "agnes/free")
    cfg = load_config()
    assert cfg.provider.base_url == "https://agnes.example/v1"
    assert cfg.provider.api_key == "test-key"
    assert cfg.provider.model == "agnes/free"


def test_default_transport_is_stdio(monkeypatch):
    for k in ["BLENDER_AGENT_API_KEY", "BLENDER_AGENT_BASE_URL", "BLENDER_AGENT_MODEL"]:
        monkeypatch.setenv(k, "x")
    cfg = load_config()
    assert cfg.blender.transport.value == "stdio"
