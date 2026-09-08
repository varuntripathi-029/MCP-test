"""Hermetic tests for MCPTestClient plumbing that don't need a live server."""
import sys

import pytest

from core.mcp_client import MCPCallResult, MCPTestClient, resolve_server_command

pytestmark = pytest.mark.unit


def test_call_result_text_concatenates_text_blocks():
    result = MCPCallResult(
        content=[
            {"type": "text", "text": "hello"},
            {"type": "image", "data": "..."},
            {"type": "text", "text": "world"},
        ],
        is_error=False,
        raw=None,
    )
    assert result.text == "hello\nworld"


def test_call_result_text_empty_when_no_text_blocks():
    result = MCPCallResult(content=[{"type": "image", "data": "..."}], is_error=False, raw=None)
    assert result.text == ""


async def test_direct_construction_raises_clear_error():
    client = MCPTestClient()
    with pytest.raises(RuntimeError, match="stdio|sse"):
        async with client:
            pass


def test_methods_require_entered_context():
    client = MCPTestClient.stdio("some-command")
    with pytest.raises(RuntimeError, match="async context manager"):
        client._require_session()


@pytest.mark.parametrize("generic", ["python", "python3"])
def test_generic_python_resolves_to_current_interpreter(generic):
    assert resolve_server_command(generic) == sys.executable


@pytest.mark.parametrize("command", ["node", "npx", "/usr/local/bin/my-server"])
def test_non_python_commands_pass_through(command):
    assert resolve_server_command(command) == command
