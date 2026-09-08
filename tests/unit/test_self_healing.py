"""Hermetic tests for SelfHealingLocator using a mocked Page and mocked LLM —
verifies the heal/retry/logging state machine without a browser or API key."""
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

import ai.self_healing as self_healing_module
from ai.self_healing import SelfHealingLocator, get_page_heal_registry

pytestmark = pytest.mark.unit


class FakePage:
    """Page stand-in: selectors listed in `working` attach, others time out."""

    def __init__(self, working: set[str], content: str = "<html><body></body></html>") -> None:
        self.working = working
        self._content = content

    def locator(self, selector: str) -> MagicMock:
        loc = MagicMock(name=f"locator({selector})")
        if selector not in self.working:
            loc.wait_for.side_effect = PlaywrightTimeoutError(f"timeout for {selector}")
        return loc

    def content(self) -> str:
        return self._content


@pytest.fixture
def llm(monkeypatch):
    stub = MagicMock()
    monkeypatch.setattr(self_healing_module, "get_llm_client", lambda: stub)
    return stub


def test_working_selector_needs_no_heal(llm):
    page = FakePage(working={"#ok"})
    healer = SelfHealingLocator(page, enabled=True)

    healer.find("the ok button", "#ok")

    llm.ask.assert_not_called()
    assert healer.heal_log == []


def test_broken_selector_healed_and_logged(llm):
    llm.ask.return_value = "#healed"
    page = FakePage(working={"#healed"})
    healer = SelfHealingLocator(page, enabled=True)

    healer.find("the submit button", "#gone")

    assert len(healer.heal_log) == 1
    record = healer.heal_log[0]
    assert record.original_selector == "#gone"
    assert record.healed_selector == "#healed"
    assert record.succeeded
    # The heal is also visible through the page-level registry the
    # conftest failure hook reads.
    assert get_page_heal_registry(page) == healer.heal_log


def test_failed_heal_raises_and_logs(llm):
    llm.ask.return_value = "#also-gone"
    page = FakePage(working=set())
    healer = SelfHealingLocator(page, enabled=True)

    with pytest.raises(PlaywrightTimeoutError):
        healer.find("a vanished element", "#gone")

    assert len(healer.heal_log) == 1
    assert not healer.heal_log[0].succeeded


def test_disabled_healer_raises_without_calling_llm(llm):
    page = FakePage(working=set())
    healer = SelfHealingLocator(page, enabled=False)

    with pytest.raises(PlaywrightTimeoutError):
        healer.find("anything", "#gone")

    llm.ask.assert_not_called()


def test_llm_failure_degrades_to_plain_timeout(llm):
    llm.ask.side_effect = RuntimeError("API down")
    page = FakePage(working=set())
    healer = SelfHealingLocator(page, enabled=True)

    with pytest.raises(PlaywrightTimeoutError):
        healer.find("anything", "#gone")

    assert healer.heal_log[0].healed_selector is None


def test_report_is_json_serializable(llm):
    llm.ask.return_value = "#healed"
    page = FakePage(working={"#healed"})
    healer = SelfHealingLocator(page, enabled=True)
    healer.find("the submit button", "#gone")

    import json

    assert json.loads(json.dumps(healer.report()))[0]["succeeded"] is True
