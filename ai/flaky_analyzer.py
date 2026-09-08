"""AI root-cause analysis for flaky tests.

Feed it a test name plus its failure logs/stack traces across N runs (pytest's
own output, network logs, screenshots' text descriptions, whatever you have)
and it proposes a likely root-cause category and a concrete fix — a much
faster starting point than a human re-reading five red CI runs.
"""
from __future__ import annotations

from dataclasses import dataclass

from ai.llm_client import get_llm_client

ANALYSIS_SYSTEM_PROMPT = """You are a test reliability engineer. Given a test
name and logs/stack traces from multiple failing runs of that test, identify
the most likely root cause category and suggest a concrete fix. Categories:
"race_condition", "hardcoded_wait", "test_data_pollution", "network_flakiness",
"selector_drift", "environment_issue", "genuine_bug", "unknown".
Respond as JSON:
{"category": "...", "confidence": 0-1, "explanation": "...", "suggested_fix": "..."}"""


@dataclass
class FlakyAnalysisReport:
    test_name: str
    category: str
    confidence: float
    explanation: str
    suggested_fix: str


class FlakyTestAnalyzer:
    def __init__(self) -> None:
        self._llm = get_llm_client()

    def analyze(self, test_name: str, run_logs: list[str]) -> FlakyAnalysisReport:
        logs_block = "\n\n---RUN---\n\n".join(run_logs)
        prompt = f"Test: {test_name}\n\nFailure logs from {len(run_logs)} runs:\n{logs_block}"
        result = self._llm.ask_json(prompt=prompt, system=ANALYSIS_SYSTEM_PROMPT)
        return FlakyAnalysisReport(
            test_name=test_name,
            category=result.get("category", "unknown"),
            confidence=float(result.get("confidence", 0)),
            explanation=result.get("explanation", ""),
            suggested_fix=result.get("suggested_fix", ""),
        )
