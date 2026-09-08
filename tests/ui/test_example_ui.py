"""Smoke tests for the Rahul Shetty practice home page."""
import pytest

from pages.example_page import PracticeHomePage


@pytest.mark.ui
@pytest.mark.smoke
def test_practice_home_loads(page):
    home = PracticeHomePage(page)
    home.open()

    assert page.title() == "QA Automation Practice Sites | Playwright, Selenium & API Testing"
    assert "Master QA Testing Through Practice" in home.hero_heading()
    assert home.browse_practice_button().is_visible()
    assert home.practice_card("AutomationPractice Portal").is_visible()
