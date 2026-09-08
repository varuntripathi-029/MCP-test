"""Example MCP tool tests. Point config/environments.yaml (or
MCP_SERVER_COMMAND / MCP_SERVER_ARGS) at your real server before running.
"""
import pytest


def _first_callable_tool(tools: list[dict]) -> dict | None:
    for tool in tools:
        schema = tool.get("input_schema") or {}
        required = schema.get("required", [])
        if not required:
            return tool
    return None


@pytest.mark.mcp
@pytest.mark.smoke
async def test_lists_available_tools(mcp_client):
    tools = await mcp_client.list_tools()
    assert isinstance(tools, list)
    if not tools:
        pytest.skip("No tools exposed by the configured MCP server")


@pytest.mark.mcp
async def test_call_tool_returns_expected_content(mcp_client):
    tools = await mcp_client.list_tools()
    if not tools:
        pytest.skip("No tools exposed by the configured MCP server")

    tool = _first_callable_tool(tools)
    if tool is None:
        pytest.skip("No tool can be called safely without arguments")

    result = await mcp_client.call_tool(tool["name"], {})
    if result.is_error:
        pytest.skip(f"Tool {tool['name']} returned a structured error for empty args")

    assert result.content, f"Tool {tool['name']} succeeded but returned no content blocks"


@pytest.mark.mcp
@pytest.mark.ai
async def test_fuzz_first_tool_for_crashes(mcp_client):
    """AI-generated adversarial inputs should never crash the server —
    they should come back as a structured MCP error, not an exception."""
    from ai.mcp_fuzzer import MCPToolFuzzer

    tools = await mcp_client.list_tools()
    if not tools:
        pytest.skip("No tools exposed by the configured MCP server")

    tool = tools[0]
    fuzzer = MCPToolFuzzer(mcp_client)
    findings = await fuzzer.fuzz_tool(tool["name"], tool["input_schema"], count=6)

    crashes = [f for f in findings if f.crashed]
    assert not crashes, f"AI fuzzing found crashes:\n{fuzzer.summarize(findings)}"
