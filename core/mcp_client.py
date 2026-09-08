"""Thin async wrapper around the official `mcp` Python SDK, purpose-built for tests.

Wraps stdio and SSE/HTTP transports behind one interface so test code doesn't
care how the server under test is launched, and exposes convenience methods
(list_tools, call_tool, list_resources, read_resource, list_prompts, get_prompt)
that return plain dicts/lists instead of SDK-internal types, which keeps
assertions in test files simple.
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

try:
    from mcp.client.sse import sse_client
except ImportError:  # pragma: no cover - older mcp SDK versions
    sse_client = None  # type: ignore[assignment]


def resolve_server_command(command: str) -> str:
    """Map a generic `python`/`python3` command to the running interpreter.

    A stdio MCP server configured as `python` must launch in the same
    virtualenv as the test run (so it sees the same installed `mcp` package),
    and bare `python` doesn't even exist on stock macOS. Any other command
    (node, npx, a binary path) is returned unchanged.
    """
    if command in ("python", "python3"):
        return sys.executable
    return command


@dataclass
class MCPCallResult:
    """Normalized result of a tool call, regardless of SDK version shape."""

    content: list[dict[str, Any]]
    is_error: bool
    raw: Any

    @property
    def text(self) -> str:
        """Concatenate all text-type content blocks — the common case in assertions."""
        return "\n".join(
            block.get("text", "") for block in self.content if block.get("type") == "text"
        )


class MCPTestClient:
    """Async context manager wrapping an MCP ClientSession for use in tests.

    Example:
        async with MCPTestClient.stdio("python", ["-m", "my_mcp_server"]) as client:
            tools = await client.list_tools()
            result = await client.call_tool("search", {"query": "playwright"})
            assert not result.is_error
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._stack = contextlib.AsyncExitStack()
        self._params: tuple[Any, ...] | None = None
        self._lifecycle_task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._startup_error: BaseException | None = None

    @classmethod
    def stdio(
        cls, command: str, args: list[str] | None = None, env: dict[str, str] | None = None
    ) -> MCPTestClient:
        client = cls()
        client._params = (
            "stdio",
            StdioServerParameters(command=resolve_server_command(command), args=args or [], env=env),
        )
        return client

    @classmethod
    def sse(cls, url: str, headers: dict[str, str] | None = None) -> MCPTestClient:
        if sse_client is None:
            raise RuntimeError("Installed `mcp` SDK version does not support SSE transport.")
        client = cls()
        client._params = ("sse", url, headers or {})
        return client

    async def _open(self) -> None:
        if self._params is None:
            raise RuntimeError(
                "MCPTestClient was constructed directly — use MCPTestClient.stdio(...) "
                "or MCPTestClient.sse(...) to configure a transport first."
            )
        kind = self._params[0]
        if kind == "stdio":
            _, server_params = self._params
            read, write = await self._stack.enter_async_context(stdio_client(server_params))
        else:
            _, url, headers = self._params
            read, write = await self._stack.enter_async_context(sse_client(url, headers=headers))

        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def _lifecycle(self) -> None:
        """Owns the transport for its entire lifetime in ONE task.

        The MCP SDK's transports use anyio cancel scopes, which must be
        entered and exited in the same asyncio task. pytest-asyncio runs
        fixture setup and teardown in *different* tasks, so opening the
        transport in setup and closing it in teardown raises
        "Attempted to exit cancel scope in a different task than it was
        entered in". Instead, this background task opens the transport,
        signals readiness, parks until stop is requested, and closes it —
        all within itself.
        """
        try:
            await self._open()
        except BaseException as exc:  # noqa: BLE001 - surfaced to start() caller
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            await self._stop.wait()
        finally:
            await self._stack.aclose()
            self._session = None

    async def start(self) -> MCPTestClient:
        """Connect. Safe to pair with aclose() from a different task."""
        self._lifecycle_task = asyncio.create_task(self._lifecycle())
        await self._ready.wait()
        if self._startup_error is not None:
            raise self._startup_error
        return self

    async def aclose(self) -> None:
        """Disconnect; counterpart to start()."""
        self._stop.set()
        if self._lifecycle_task is not None:
            await self._lifecycle_task

    async def __aenter__(self) -> MCPTestClient:
        return await self.start()

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    def _require_session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCPTestClient must be used as an async context manager before calling it.")
        return self._session

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._require_session().list_tools()
        return [
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> MCPCallResult:
        result = await self._require_session().call_tool(name, arguments or {})
        content = [block.model_dump() for block in result.content]
        return MCPCallResult(content=content, is_error=bool(getattr(result, "isError", False)), raw=result)

    async def list_resources(self) -> list[dict[str, Any]]:
        result = await self._require_session().list_resources()
        return [
            {"uri": str(r.uri), "name": r.name, "mime_type": r.mimeType} for r in result.resources
        ]

    async def read_resource(self, uri: str) -> list[dict[str, Any]]:
        result = await self._require_session().read_resource(AnyUrl(uri))
        return [c.model_dump() for c in result.contents]

    async def list_prompts(self) -> list[dict[str, Any]]:
        result = await self._require_session().list_prompts()
        return [
            {"name": p.name, "description": p.description, "arguments": p.arguments}
            for p in result.prompts
        ]

    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> list[dict[str, Any]]:
        result = await self._require_session().get_prompt(name, arguments or {})
        return [m.model_dump() for m in result.messages]
