"""Playwright browser/context lifecycle management, kept separate from pytest
fixtures so it can also be driven by non-pytest tools (e.g. the AI exploratory
agent in ai/nl_test_generator.py).
"""
from __future__ import annotations

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from config.settings import settings


class BrowserManager:
    def __init__(self, browser_name: str = "chromium", headless: bool | None = None) -> None:
        self.browser_name = browser_name
        self.headless = settings.headless if headless is None else headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def start(self) -> Browser:
        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, self.browser_name)
        self._browser = browser_type.launch(headless=self.headless)
        return self._browser

    def new_context(self, **kwargs) -> BrowserContext:
        browser = self._browser or self.start()
        return browser.new_context(**kwargs)

    def new_page(self, context: BrowserContext | None = None) -> Page:
        ctx = context or self.new_context()
        return ctx.new_page()

    def stop(self) -> None:
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self) -> BrowserManager:
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
