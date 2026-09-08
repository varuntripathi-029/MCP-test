from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.sync_api import BrowserContext, Page

from ai.flaky_analyzer import FlakyTestAnalyzer
from ai.self_healing import SelfHealingLocator, get_page_heal_registry
from ai.visual_ai import VisualAIComparator
from config.settings import settings
from core.browser_manager import BrowserManager
from core.mcp_client import MCPTestClient, resolve_server_command
from utils.reporter import write_ai_artifact
from utils.screenshot_helper import capture

# --------------------------------------------------------------------------
# Playwright / UI fixtures
# --------------------------------------------------------------------------

# Module scope, NOT session scope: the sync Playwright API keeps an asyncio
# loop "running" on the main thread for as long as the browser is alive, which
# makes every pytest-asyncio test that runs after a UI test fail with
# "Runner.run() cannot be called from a running event loop". Scoping the
# browser to the requesting test module still reuses one browser across all
# tests in a UI module but tears it down before other modules' async tests
# run. (Package scope doesn't work here: tests/__init__.py makes the whole
# tests/ tree one package, deferring teardown to the end of the session.)
@pytest.fixture(scope="module")
def browser_manager() -> Iterator[BrowserManager]:
    with BrowserManager(headless=settings.headless) as manager:
        yield manager


@pytest.fixture
def context(browser_manager: BrowserManager) -> Iterator[BrowserContext]:
    ctx = browser_manager.new_context()
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Iterator[Page]:
    pg = context.new_page()
    yield pg
    pg.close()


@pytest.fixture
def self_healing(page: Page) -> SelfHealingLocator:
    return SelfHealingLocator(page, enabled=settings.ai_self_healing_enabled)


# --------------------------------------------------------------------------
# MCP fixtures
# --------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mcp_client():
    """Connects to the MCP server configured in config/environments.yaml
    (or MCP_SERVER_COMMAND/MCP_SERVER_ARGS env vars) for the active TEST_ENV.

    Skips (rather than errors) when no runnable server is configured, so a
    fresh clone stays green until the user points the config at a real server.
    """
    cfg = settings.mcp_server
    if cfg.transport == "stdio":
        if not cfg.command:
            pytest.skip(
                "No MCP server configured — set MCP_SERVER_COMMAND/MCP_SERVER_ARGS "
                "or the mcp_server block in config/environments.yaml."
            )
        if shutil.which(resolve_server_command(cfg.command)) is None:
            pytest.skip(
                f"MCP server command {cfg.command!r} not found on PATH — "
                "update MCP_SERVER_COMMAND or config/environments.yaml."
            )
        # Resolve args that name files in this repo (e.g. examples/demo_server.py)
        # to absolute paths, so the server launches no matter which directory
        # pytest was invoked from.
        root = Path(__file__).resolve().parent
        args = [str(root / a) if (root / a).exists() else a for a in cfg.args]
        client = MCPTestClient.stdio(cfg.command, args)
    else:
        if not cfg.url:
            pytest.skip(
                "MCP transport is SSE but no URL configured — set the mcp_server.url "
                "in config/environments.yaml for the active TEST_ENV."
            )
        client = MCPTestClient.sse(cfg.url)

    async with client as connected:
        yield connected


# --------------------------------------------------------------------------
# AI-assisted fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def visual_ai() -> VisualAIComparator:
    return VisualAIComparator(ai_enabled=settings.ai_visual_triage_enabled)


@pytest.fixture
def flaky_analyzer() -> FlakyTestAnalyzer:
    return FlakyTestAnalyzer()


# --------------------------------------------------------------------------
# Failure hooks: screenshot + self-heal report on any failed test
# --------------------------------------------------------------------------

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page is not None and settings.screenshot_on_failure:
            capture(page, item.name)

        # Collect heals from every SelfHealingLocator attached to the page
        # (page objects included), not just the `self_healing` fixture.
        records = []
        if page is not None:
            records = get_page_heal_registry(page) or []
        if not records:
            healing = item.funcargs.get("self_healing")
            if healing is not None:
                records = healing.heal_log
        if records:
            write_ai_artifact(f"{item.name}_self_heal", [r.__dict__ for r in records])
