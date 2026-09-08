"""LLM-as-judge assertions for outputs that don't have one exact-match answer.

Useful for MCP tools/agents whose responses are natural language (a summary,
a generated answer, an LLM-backed tool's own output) where exact string
equality is too brittle but you still want an automated pass/fail. Use
sparingly and prefer real assertions wherever a deterministic check is
possible — this is an escape hatch, not the default.
"""
from __future__ import annotations

from dataclasses import dataclass

from ai.llm_client import get_llm_client

JUDGE_SYSTEM_PROMPT = """You are a strict test oracle. Given an actual output
and a natural-language description of what is expected, decide whether the
actual output satisfies the expectation. Be strict: partial or vague matches
that a careful human reviewer would reject should fail. Respond as JSON:
{"pass": true|false, "confidence": 0-1, "reason": "..."}"""

SUGGEST_SYSTEM_PROMPT = """You are a test design assistant. Given a
description of a page, API response, or test context, suggest a list of
concrete, automatable assertions a test could make. Respond as a JSON array
of strings, each one a specific assertion (e.g. "response status is 200",
"page title contains 'Dashboard'")."""


@dataclass
class JudgeVerdict:
    passed: bool
    confidence: float
    reason: str


class AssertionOracle:
    def __init__(self) -> None:
        self._llm = get_llm_client()

    def verify_semantic(self, actual: str, expected_description: str) -> JudgeVerdict:
        prompt = f"Actual output:\n{actual}\n\nExpected: {expected_description}"
        result = self._llm.ask_json(prompt=prompt, system=JUDGE_SYSTEM_PROMPT)
        return JudgeVerdict(
            passed=bool(result.get("pass", False)),
            confidence=float(result.get("confidence", 0)),
            reason=result.get("reason", ""),
        )

    def suggest_assertions(self, context: str) -> list[str]:
        return self._llm.ask_json(prompt=context, system=SUGGEST_SYSTEM_PROMPT)


def assert_semantic(actual: str, expected_description: str, min_confidence: float = 0.7) -> None:
    """Pytest-friendly helper: raises AssertionError with the LLM's reasoning on failure."""
    verdict = AssertionOracle().verify_semantic(actual, expected_description)
    if not verdict.passed or verdict.confidence < min_confidence:
        raise AssertionError(
            f"Semantic assertion failed (confidence={verdict.confidence:.2f}): {verdict.reason}\n"
            f"Expected: {expected_description}\nActual: {actual}"
        )
