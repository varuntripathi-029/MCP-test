"""Tiny MCP server the test suite runs against out of the box.

This exists so a fresh clone has a real Model Context Protocol server to test:
`config/environments.yaml` points the `local` and `ci` environments here, which
turns the tests in tests/mcp/ from skips into genuine green runs. Swap the
config to your own server when you have one — this file is also the minimal
reference for what the framework expects a server to expose (tools with and
without required arguments, a resource, a prompt).

Run it manually for debugging with:  python examples/demo_server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("demo-server")


@mcp.tool()
def ping() -> str:
    """Health check. Takes no arguments — exercised by tests that need a
    tool callable with an empty argument dict."""
    return "pong"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers. Has required, typed arguments — the fuzzer's target."""
    return a + b


@mcp.tool()
def echo(text: str) -> str:
    """Echo the input back. Simple string round-trip for content assertions."""
    return f"echo: {text}"


@mcp.resource("demo://greeting")
def greeting() -> str:
    """A static resource so list_resources/read_resource have something real."""
    return "Hello from the demo MCP server!"


@mcp.prompt()
def summarize(topic: str) -> str:
    """A prompt template so list_prompts/get_prompt have something real."""
    return f"Write a one-paragraph summary of: {topic}"


if __name__ == "__main__":
    mcp.run()  # stdio transport — what MCPTestClient.stdio() speaks
