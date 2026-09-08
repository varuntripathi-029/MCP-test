"""Base Page Object. Wraps the AI self-healing locator so every page object
gets it for free — pass a plain-English description alongside your primary
selector and failures get one AI-assisted retry before failing the test."""
from __future__ import annotations

from playwright.sync_api import Locator, Page

from ai.self_healing import SelfHealingLocator
from config.settings import settings


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.healing = SelfHealingLocator(page, enabled=settings.ai_self_healing_enabled)

    def goto(self, path: str = "") -> None:
        self.page.goto(f"{settings.base_url}{path}")

    def find(self, description: str, selector: str) -> Locator:
        return self.healing.find(description, selector)
