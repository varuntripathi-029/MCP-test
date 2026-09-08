"""Hermetic tests for LLMClient plumbing that don't hit the API."""
import pytest

from ai.llm_client import LLMClient, strip_code_fences

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('  \n```json\n[1, 2]\n```\n  ', "[1, 2]"),
    ],
)
def test_strip_code_fences(raw, expected):
    assert strip_code_fences(raw) == expected


def test_missing_api_key_raises_actionable_error(monkeypatch):
    monkeypatch.setattr("config.settings.settings.anthropic_api_key", None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        LLMClient()
