"""Hermetic tests for TestDataGenerator with a mocked LLM — verifies the
jsonschema validation gate without an API key."""
from unittest.mock import MagicMock

import jsonschema
import pytest

import ai.synthetic_data_generator as gen_module
from ai.synthetic_data_generator import TestDataGenerator

pytestmark = pytest.mark.unit

SCHEMA = {
    "type": "object",
    "properties": {
        "email": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["email", "age"],
}


@pytest.fixture
def llm(monkeypatch):
    stub = MagicMock()
    monkeypatch.setattr(gen_module, "get_llm_client", lambda: stub)
    return stub


def test_returns_llm_records(llm):
    llm.ask_json.return_value = [{"email": "a@b.c", "age": 30}]
    records = TestDataGenerator().generate(SCHEMA, count=1)
    assert records == [{"email": "a@b.c", "age": 30}]


def test_validate_accepts_conforming_records(llm):
    llm.ask_json.return_value = [{"email": "a@b.c", "age": 0}, {"email": "d@e.f", "age": 130}]
    records = TestDataGenerator().generate(SCHEMA, count=2, validate=True)
    assert len(records) == 2


def test_validate_rejects_nonconforming_records(llm):
    llm.ask_json.return_value = [{"email": "a@b.c", "age": -5}]  # violates minimum
    with pytest.raises(jsonschema.ValidationError):
        TestDataGenerator().generate(SCHEMA, count=1, validate=True)


def test_notes_are_passed_into_prompt(llm):
    llm.ask_json.return_value = []
    TestDataGenerator().generate(SCHEMA, count=3, notes="all emails on example.org")
    prompt = llm.ask_json.call_args.kwargs["prompt"]
    assert "all emails on example.org" in prompt
