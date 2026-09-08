"""Attaches AI-derived artifacts (self-heal logs, visual triage verdicts,
flaky-test root-cause reports) to pytest-html so they show up next to the
normal pass/fail output instead of living only in test-run logs.
"""
from __future__ import annotations

import json
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def write_ai_artifact(name: str, data: dict | list) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, default=str))
    return path
