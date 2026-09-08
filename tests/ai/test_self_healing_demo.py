"""Demonstrates each AI module in isolation. These require ANTHROPIC_API_KEY
and are marked `ai` so they can be excluded from fast local/CI runs with
`-m "not ai"`.
"""
import pytest

from ai.assertion_oracle import AssertionOracle
from ai.synthetic_data_generator import TestDataGenerator


@pytest.mark.ai
def test_assertion_oracle_semantic_pass():
    oracle = AssertionOracle()
    verdict = oracle.verify_semantic(
        actual="Order #1234 shipped on 2026-07-09 via FedEx, arriving 2026-07-12.",
        expected_description="a shipping confirmation that includes a carrier and an estimated arrival date",
    )
    assert verdict.passed, verdict.reason


@pytest.mark.ai
def test_assertion_oracle_semantic_fail():
    oracle = AssertionOracle()
    verdict = oracle.verify_semantic(
        actual="Your cart is empty.",
        expected_description="a shipping confirmation that includes a carrier and an estimated arrival date",
    )
    assert not verdict.passed


@pytest.mark.ai
def test_generates_synthetic_records_matching_schema():
    schema = {
        "type": "object",
        "properties": {
            "email": {"type": "string", "format": "email"},
            "age": {"type": "integer", "minimum": 0, "maximum": 130},
        },
        "required": ["email", "age"],
    }
    records = TestDataGenerator().generate(schema, count=3)
    assert len(records) == 3
    for record in records:
        assert "email" in record and "age" in record
