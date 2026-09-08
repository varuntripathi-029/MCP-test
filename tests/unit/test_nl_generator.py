"""Hermetic tests for NLTestGenerator's code renderer — no LLM involved,
the renderer is pure and must produce valid Python for hostile inputs."""
import ast

import pytest

from ai.nl_test_generator import GeneratedStep, NLTestGenerator

pytestmark = pytest.mark.unit


def render(steps: list[dict], **kwargs) -> str:
    return NLTestGenerator.to_pytest_playwright_source([GeneratedStep(s) for s in steps], **kwargs)


def test_renders_all_supported_actions_as_valid_python():
    source = render(
        [
            {"action": "goto", "value": "https://example.com"},
            {"action": "click", "selector": "#submit"},
            {"action": "fill", "selector": "input[name=q]", "value": "playwright"},
            {"action": "check", "selector": "#agree"},
            {"action": "select", "selector": "#country", "value": "NZ"},
            {"action": "assert_visible", "selector": ".result"},
            {"action": "assert_text", "selector": "h1", "value": "Results"},
        ]
    )
    ast.parse(source)  # must be syntactically valid
    assert 'page.goto(\'https://example.com\')' in source
    assert "page.locator('#submit').click()" in source


def test_quotes_in_llm_output_do_not_break_generated_code():
    """Selectors/values come from an LLM — embedded quotes must be escaped,
    not interpolated into broken or executable code."""
    source = render(
        [
            {"action": "fill", "selector": 'input[title="x"]', "value": 'he said "hi"'},
            {"action": "click", "selector": "button\"); import os  # injection attempt"},
        ]
    )
    tree = ast.parse(source)  # would raise SyntaxError before the fix
    # The hostile text must survive only as a string literal, never as code.
    assert all(not isinstance(node, ast.Import) for node in ast.walk(tree))


def test_unrecognized_action_becomes_comment():
    source = render([{"action": "teleport", "selector": "#x"}])
    ast.parse(source)
    assert "# unrecognized step" in source


def test_custom_test_name():
    source = render([{"action": "goto", "value": "https://example.com"}], test_name="test_login")
    assert source.startswith("def test_login(page):")
