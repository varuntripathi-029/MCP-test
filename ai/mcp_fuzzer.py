"""AI-driven edge-case fuzzing for MCP tool inputs.

Given an MCP tool's JSON input_schema, ask the LLM to propose adversarial and
boundary-condition argument sets (type confusion, injection strings, unicode,
oversized payloads, missing required fields, nested-object edge cases) that a
human would eventually think of but slower. Execute them against a live
MCPTestClient and flag any that return a raw 500-style crash / unhandled
exception rather than a clean validation error — that gap is the actual bug
this technique is designed to catch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai.llm_client import get_llm_client
from core.mcp_client import MCPCallResult, MCPTestClient

SYSTEM_PROMPT = """You are a fuzz-testing assistant for MCP (Model Context
Protocol) tools. Given a tool's JSON input_schema, generate an array of
adversarial argument objects designed to find validation gaps and crashes:
wrong types, missing required fields, empty strings, huge strings, negative
numbers where positive is expected, SQL/command injection strings, unicode
and emoji, deeply nested objects, null where not allowed, extra unexpected
fields. Respond with ONLY a JSON array of argument objects (each one is a
full arguments dict to pass to the tool)."""


@dataclass
class FuzzFinding:
    tool_name: str
    arguments: dict[str, Any]
    result: MCPCallResult | None
    crashed: bool
    error: str | None


class MCPToolFuzzer:
    def __init__(self, client: MCPTestClient) -> None:
        self.client = client
        self._llm = get_llm_client()

    def generate_edge_cases(self, tool_name: str, input_schema: dict, count: int = 8) -> list[dict]:
        prompt = (
            f"Tool name: {tool_name}\nInput schema:\n{input_schema}\n\n"
            f"Generate {count} adversarial argument sets."
        )
        return self._llm.ask_json(prompt=prompt, system=SYSTEM_PROMPT)

    async def fuzz_tool(self, tool_name: str, input_schema: dict, count: int = 8) -> list[FuzzFinding]:
        """Generate edge cases and execute each against the live MCP server.

        A finding is flagged `crashed=True` when the server raises an
        unhandled exception (transport-level failure) rather than returning a
        structured MCP error result — that distinction is what separates
        "the server validated input correctly" from "the server crashed."
        """
        edge_cases = self.generate_edge_cases(tool_name, input_schema, count)
        findings: list[FuzzFinding] = []
        for args in edge_cases:
            try:
                result = await self.client.call_tool(tool_name, args)
                findings.append(FuzzFinding(tool_name, args, result, crashed=False, error=None))
            except Exception as exc:  # noqa: BLE001 - the crash itself is the finding
                findings.append(FuzzFinding(tool_name, args, None, crashed=True, error=str(exc)))
        return findings

    @staticmethod
    def summarize(findings: list[FuzzFinding]) -> str:
        crashes = [f for f in findings if f.crashed]
        clean_errors = [f for f in findings if not f.crashed and f.result and f.result.is_error]
        unexpected_success = [f for f in findings if not f.crashed and f.result and not f.result.is_error]
        return (
            f"{len(findings)} edge cases run: "
            f"{len(crashes)} crashed (bug), "
            f"{len(clean_errors)} returned a validation error (expected), "
            f"{len(unexpected_success)} succeeded (review for validation gaps)."
        )
