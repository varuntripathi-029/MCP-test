from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / "config" / "environments.yaml"


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class MCPServerConfig:
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None


@dataclass
class Settings:
    # default_factory (not a plain default) so the environment is read each
    # time a Settings is constructed — a plain `= os.getenv(...)` default is
    # evaluated once at class-definition time and ignores later env changes,
    # which breaks tests that monkeypatch the environment and call load().
    env_name: str = field(default_factory=lambda: os.getenv("TEST_ENV", "local"))
    base_url: str = field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:3000"))
    headless: bool = field(default_factory=lambda: _env_bool("HEADLESS", True))
    screenshot_on_failure: bool = field(default_factory=lambda: _env_bool("SCREENSHOT_ON_FAILURE", True))

    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-5"))
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))

    ai_self_healing_enabled: bool = field(
        default_factory=lambda: _env_bool("AI_SELF_HEALING_ENABLED", True))
    ai_visual_triage_enabled: bool = field(
        default_factory=lambda: _env_bool("AI_VISUAL_TRIAGE_ENABLED", True))
    ai_flaky_analysis_enabled: bool = field(
        default_factory=lambda: _env_bool("AI_FLAKY_ANALYSIS_ENABLED", True))

    mcp_server: MCPServerConfig = field(default_factory=MCPServerConfig)

    @classmethod
    def load(cls, env_name: str | None = None, config_file: Path | None = None) -> Settings:
        settings = cls()
        env_name = env_name or settings.env_name
        config_file = config_file or ENV_FILE

        if config_file.exists():
            data = yaml.safe_load(config_file.read_text()) or {}
            env_data = data.get(env_name, {})
            if "base_url" in env_data:
                settings.base_url = env_data["base_url"]
            if "headless" in env_data:
                settings.headless = bool(env_data["headless"])
            mcp_data = env_data.get("mcp_server", {})
            if mcp_data:
                settings.mcp_server = MCPServerConfig(
                    transport=mcp_data.get("transport", "stdio"),
                    command=mcp_data.get("command"),
                    args=mcp_data.get("args", []),
                    url=mcp_data.get("url"),
                )

        # Environment variables always win over the YAML file.
        if os.getenv("BASE_URL"):
            settings.base_url = os.getenv("BASE_URL", settings.base_url)
        if os.getenv("HEADLESS"):
            settings.headless = _env_bool("HEADLESS", settings.headless)
        if os.getenv("MCP_SERVER_COMMAND"):
            settings.mcp_server.command = os.getenv("MCP_SERVER_COMMAND")
        if os.getenv("MCP_SERVER_ARGS"):
            settings.mcp_server.args = os.getenv("MCP_SERVER_ARGS", "").split(",")

        settings.env_name = env_name
        return settings


settings = Settings.load()
