"""Custom states — shows how to subclass State for domain-specific conditions.

Run:
    uv run python examples/custom_state.py
"""

from __future__ import annotations

from playwright.async_api import Page, Response

import yoink
from yoink import Request
from yoink.states import State


class PageTitleContains(State):
    """Resolves when the page <title> contains the given substring."""

    def __init__(self, substring: str) -> None:
        self.substring = substring

    async def check(self, page: Page, response: Response | None) -> bool:
        title = await page.title()
        return self.substring.lower() in title.lower()


class MinElements(State):
    """Resolves when at least N elements matching a CSS selector are present."""

    def __init__(self, selector: str, count: int = 1) -> None:
        self.selector = selector
        self.count = count

    async def check(self, page: Page, response: Response | None) -> bool:
        n = await page.locator(self.selector).count()
        return n >= self.count


class BodyTextContains(State):
    """Resolves when the page body text contains the given string."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def check(self, page: Page, response: Response | None) -> bool:
        body = await page.inner_text("body")
        return self.text in body


if __name__ == "__main__":
    print("=== PageTitleContains ===")
    req = Request(url="https://example.com", state=PageTitleContains("example"))
    results = yoink.get_all([req])
    r = results[0]
    print(f"  ok={r.ok}  terminal={r.terminal}")

    print("\n=== MinElements (h1 on example.com) ===")
    req2 = Request(url="https://example.com", state=MinElements("h1", count=1))
    results2 = yoink.get_all([req2])
    r2 = results2[0]
    print(f"  ok={r2.ok}  terminal={r2.terminal}")

    print("\n=== Composing custom states ===")
    composed = PageTitleContains("example") & MinElements("h1")
    req3 = Request(url="https://example.com", state=composed)
    results3 = yoink.get_all([req3])
    r3 = results3[0]
    print(f"  ok={r3.ok}  terminal={r3.terminal}")

    print("\nDone.")
