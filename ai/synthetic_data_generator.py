"""AI-generated synthetic test data.

Given a JSON schema (or a plain description) plus optional constraints,
produce realistic-looking test records — useful for form-fill tests, MCP tool
argument fuzzing, and seeding fixtures without hand-writing dozens of
near-duplicate literals.
"""
from __future__ import annotations

import jsonschema

from ai.llm_client import get_llm_client

SYSTEM_PROMPT = """You generate synthetic test data. Given a JSON schema and a
record count, produce a JSON array of that many records conforming to the
schema. Vary values realistically (names, emails, dates, etc.) and include at
least one boundary/edge-case record (empty string, max length, unicode,
negative number) if the schema allows it. Respond with ONLY the JSON array."""


class TestDataGenerator:
    __test__ = False  # not a pytest test case — name just happens to start with "Test"

    def __init__(self) -> None:
        self._llm = get_llm_client()

    def generate(
        self, schema: dict, count: int = 5, notes: str | None = None, validate: bool = False
    ) -> list[dict]:
        """Generate `count` records for `schema`.

        With validate=True, every record is checked against the schema with
        jsonschema and a ValidationError is raised if the model produced a
        non-conforming record — recommended whenever the schema is strict
        enough to express what "valid" means.
        """
        prompt = f"JSON schema:\n{schema}\n\nGenerate {count} records."
        if notes:
            prompt += f"\n\nAdditional constraints: {notes}"
        records = self._llm.ask_json(prompt=prompt, system=SYSTEM_PROMPT)
        if validate:
            for record in records:
                jsonschema.validate(record, schema)
        return records
