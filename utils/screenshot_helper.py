from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "reports" / "screenshots"


def capture(page: Page, name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def baseline_path(name: str) -> Path:
    baseline_dir = SCREENSHOT_DIR.parent / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    return baseline_dir / f"{name}.png"
