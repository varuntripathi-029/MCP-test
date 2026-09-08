"""Natural-language -> executable test steps.

Lets a tester write a scenario in English and get back a structured list of
either Playwright UI actions or MCP tool calls. This is a generation-time aid
(you review and commit the output as a real test / page-object method) — it
is intentionally NOT wired to execute unreviewed AI output directly against a
target, since that would blur the line between "AI writes the test" and
"AI is the test."
"""
from __future__ import annotations

from dataclasses import dataclass

from ai.llm_client import get_llm_client

UI_SYSTEM_PROMPT = """You convert a plain-English test scenario into a JSON
list of Playwright actions. Each step is an object:
{"action": "goto"|"click"|"fill"|"check"|"select"|"assert_visible"|"assert_text",
 "selector": "<css or role-based selector, omit for goto>",
 "value": "<text/url, omit if not applicable>"}
Prefer role- and text-based selectors (get_by_role, get_by_text semantics)
over brittle CSS. Respond with ONLY the JSON array."""

MCP_SYSTEM_PROMPT = """You convert a plain-English test scenario for an MCP
(Model Context Protocol) server into a JSON list of steps. Each step is:
{"action": "call_tool"|"read_resource"|"get_prompt"|"assert_contains"|"assert_no_error",
 "name": "<tool/resource/prompt name, omit for assert steps>",
 "arguments": {...arguments dict, omit if none},
 "expected": "<substring or condition to assert, omit if not applicable>"}
Base tool/resource names on the provided catalog when one is given; do not
invent names that aren't in the catalog. Respond with ONLY the JSON array."""


@dataclass
class GeneratedStep:
    raw: dict

    def __repr__(self) -> str:
        return f"GeneratedStep({self.raw})"


class NLTestGenerator:
    """Generation-time helper — output is meant to be reviewed before being
    committed as a real test, not executed sight-unseen in CI."""

    def __init__(self) -> None:
        self._llm = get_llm_client()

    def generate_ui_steps(self, scenario: str) -> list[GeneratedStep]:
        steps = self._llm.ask_json(prompt=scenario, system=UI_SYSTEM_PROMPT)
        return [GeneratedStep(s) for s in steps]

    def generate_mcp_steps(
        self, scenario: str, tool_catalog: list[dict] | None = None
    ) -> list[GeneratedStep]:
        prompt = scenario
        if tool_catalog:
            prompt += f"\n\nAvailable tools/resources catalog:\n{tool_catalog}"
        steps = self._llm.ask_json(prompt=prompt, system=MCP_SYSTEM_PROMPT)
        return [GeneratedStep(s) for s in steps]

    @staticmethod
    def to_pytest_playwright_source(steps: list[GeneratedStep], test_name: str = "test_generated") -> str:
        """Render generated UI steps as literal pytest+Playwright source for a human to review and commit.

        Selectors and values come from an LLM, so they are quoted with repr()
        — a stray quote in a generated value must not produce syntactically
        broken (or unintentionally executable) Python.
        """
        lines = [f"def {test_name}(page):"]
        for step in steps:
            s = step.raw
            action = s.get("action")
            selector = repr(str(s.get("selector", "")))
            value = repr(str(s.get("value", "")))
            if action == "goto":
                lines.append(f"    page.goto({value})")
            elif action == "click":
                lines.append(f"    page.locator({selector}).click()")
            elif action == "fill":
                lines.append(f"    page.locator({selector}).fill({value})")
            elif action == "check":
                lines.append(f"    page.locator({selector}).check()")
            elif action == "select":
                lines.append(f"    page.locator({selector}).select_option({value})")
            elif action == "assert_visible":
                lines.append(f"    assert page.locator({selector}).is_visible()")
            elif action == "assert_text":
                lines.append(f"    assert {value} in page.locator({selector}).inner_text()")
            else:
                # `pass` keeps the function valid Python even if every step
                # was unrecognized (a comment alone is not a function body).
                lines.append(f"    pass  # unrecognized step: {s!r}")
        return "\n".join(lines)
