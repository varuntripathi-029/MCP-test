from __future__ import annotations

from pages.base_page import BasePage


class PracticeHomePage(BasePage):
    """Page object for the Rahul Shetty practice home page."""

    def open(self) -> None:
        self.goto("")

    def hero_heading(self) -> str:
        return self.find(
            description="the main page heading for the practice home page",
            selector='h1:has-text("Master QA Testing Through Practice")',
        ).inner_text()

    def browse_practice_button(self):
        return self.find(
            description="the button that opens the practice sites and resources section",
            selector='button:has-text("Browse Practice sites & Resources")',
        )

    def practice_card(self, title: str):
        return self.find(
            description=f'the practice card titled {title}',
            selector=f'h3:has-text("{title}")',
        )
