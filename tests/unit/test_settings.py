"""Hermetic tests for Settings loading: YAML + env-var precedence."""
import pytest

from config.settings import Settings, _env_bool

pytestmark = pytest.mark.unit

YAML = """
local:
  base_url: "https://yaml.example.com"
  headless: false
  mcp_server:
    transport: stdio
    command: "python3"
    args: ["-m", "demo_server"]

staging:
  base_url: "https://staging.example.com"
  mcp_server:
    transport: sse
    url: "https://staging.example.com/mcp"
"""


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "environments.yaml"
    path.write_text(YAML)
    return path


def test_yaml_values_loaded_for_active_env(config_file, monkeypatch):
    for var in ("BASE_URL", "HEADLESS", "MCP_SERVER_COMMAND", "MCP_SERVER_ARGS"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings.load(env_name="local", config_file=config_file)

    assert settings.base_url == "https://yaml.example.com"
    assert settings.headless is False
    assert settings.mcp_server.command == "python3"
    assert settings.mcp_server.args == ["-m", "demo_server"]


def test_env_name_switches_block(config_file, monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)

    settings = Settings.load(env_name="staging", config_file=config_file)

    assert settings.base_url == "https://staging.example.com"
    assert settings.mcp_server.transport == "sse"
    assert settings.mcp_server.url == "https://staging.example.com/mcp"


def test_env_vars_override_yaml(config_file, monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://from-env:9999")
    monkeypatch.setenv("MCP_SERVER_COMMAND", "node")
    monkeypatch.setenv("MCP_SERVER_ARGS", "server.js,--verbose")

    settings = Settings.load(env_name="local", config_file=config_file)

    assert settings.base_url == "http://from-env:9999"
    assert settings.mcp_server.command == "node"
    assert settings.mcp_server.args == ["server.js", "--verbose"]


def test_missing_config_file_falls_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)

    settings = Settings.load(env_name="local", config_file=tmp_path / "nope.yaml")

    assert settings.base_url == "http://localhost:3000"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("false", False), ("", False)],
)
def test_env_bool_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("SOME_FLAG", value)
    assert _env_bool("SOME_FLAG") is expected


def test_env_bool_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert _env_bool("SOME_FLAG", default=True) is True
    assert _env_bool("SOME_FLAG", default=False) is False
