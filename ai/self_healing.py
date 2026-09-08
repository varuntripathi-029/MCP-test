"""AI self-healing locators for Playwright.

When a selector that used to work breaks (DOM refactor, id churn, class name
change), instead of failing the test outright we hand the page's DOM and the
element's plain-English description to the LLM and ask for a replacement
selector, then retry once. Every heal is logged so a human can turn it into a
permanent fix in the page object rather than silently relying on AI forever.
"""
from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ai.llm_client import get_llm_client
from utils.logger import get_logger

logger = get_logger(__name__)

HEAL_SYSTEM_PROMPT = """You are a Playwright locator repair assistant.
Given a trimmed HTML snapshot of a page and a plain-English description of the
element a test wants to interact with, return the single best CSS selector or
Playwright locator string that matches that element. Prefer robust, semantic
selectors (role, text, test-id) over brittle ones (nth-child, generated class
names). Return ONLY the selector string, nothing else."""


@dataclass
class HealRecord:
    description: str
    original_selector: str
    healed_selector: str | None
    succeeded: bool


def get_page_heal_registry(page: Page, create: bool = False) -> list[HealRecord] | None:
    """Per-Page shared list of heal records, so reporting hooks can collect
    heals from every SelfHealingLocator attached to the same page."""
    registry = getattr(page, "_self_heal_records", None)
    if registry is None and create:
        registry = []
        try:
            page._self_heal_records = registry  # type: ignore[attr-defined]
        except AttributeError:  # exotic Page proxies that reject new attributes
            return None
    return registry


class SelfHealingLocator:
    """Wraps a Playwright Page; falls back to an LLM-proposed selector on failure."""

    def __init__(self, page: Page, enabled: bool = True, max_dom_chars: int = 12000) -> None:
        self.page = page
        self.enabled = enabled
        self.max_dom_chars = max_dom_chars
        self.heal_log: list[HealRecord] = []
        # Also register heals on the Page itself so the conftest failure hook
        # can find them no matter which object created this locator (the
        # `self_healing` fixture, a BasePage, or ad-hoc construction).
        self._page_registry = get_page_heal_registry(page, create=True)

    def _record(self, record: HealRecord) -> None:
        self.heal_log.append(record)
        if self._page_registry is not None and record not in self._page_registry:
            self._page_registry.append(record)

    def find(self, description: str, selector: str, timeout: int = 5000):
        """Try `selector` first; on timeout, ask the LLM to propose a replacement
        based on `description`, retry once, and record the outcome either way."""
        locator = self.page.locator(selector)
        try:
            locator.wait_for(state="attached", timeout=timeout)
            return locator
        except PlaywrightTimeoutError:
            if not self.enabled:
                raise

        logger.warning("Selector %r failed for %r — attempting AI self-heal", selector, description)
        healed_selector = self._propose_selector(description)
        record = HealRecord(description, selector, healed_selector, succeeded=False)

        if healed_selector:
            healed_locator = self.page.locator(healed_selector)
            try:
                healed_locator.wait_for(state="attached", timeout=timeout)
                record.succeeded = True
                self._record(record)
                logger.info("Self-heal succeeded: %r -> %r", selector, healed_selector)
                return healed_locator
            except PlaywrightTimeoutError:
                pass

        self._record(record)
        raise PlaywrightTimeoutError(
            f"Selector {selector!r} failed and AI self-heal could not find "
            f"a working replacement for: {description!r}"
        )

    def _propose_selector(self, description: str) -> str | None:
        dom = self.page.content()[: self.max_dom_chars]
        prompt = f"HTML snapshot:\n{dom}\n\nElement description: {description}\n\nSelector:"
        try:
            selector = get_llm_client().ask(prompt, system=HEAL_SYSTEM_PROMPT, max_tokens=200)
            return selector.strip().strip("`")
        except Exception as exc:  # noqa: BLE001 - AI failure must not crash the test run
            logger.error("AI self-heal request failed: %s", exc)
            return None

    def report(self) -> list[dict]:
        """Summary for attaching to HTML/CI reports — surfaces every heal, pass or fail."""
        return [r.__dict__ for r in self.heal_log]
