"""Scroll-and-scrape — demonstrates pre/post navigation actions.

Shows how to use actions to interact with a page before and after navigation,
useful for sites that lazy-load content on scroll.

Run:
    uv run python examples/scroll_and_scrape.py
"""

from __future__ import annotations

import yoink
from yoink import (
    Click,
    EvaluateJS,
    Request,
    Scroll,
    ScrollToBottom,
    Selector,
    Wait,
)


def scrape_with_scroll(url: str) -> None:
    print(f"Fetching: {url}")
    req = Request(
        url=url,
        # post-navigate: scroll to trigger lazy-loaded content, then wait for it
        actions=[
            ScrollToBottom(step_px=400, delay_ms=80),
            Wait(ms=300),
        ],
        state=Selector("h1"),
        timeout=30.0,
    )
    results = yoink.get_all([req])
    r = results[0]
    print(f"  ok={r.ok}  terminal={r.terminal}  {r.duration_ms}ms  {len(r.html)} bytes")


def scrape_with_pre_actions(url: str) -> None:
    """Demonstrate pre_actions: inject JS before goto to e.g. bypass consent banners."""
    print(f"\nFetching with pre_actions: {url}")
    req = Request(
        url=url,
        # pre_actions run before page.goto — set up route interceptors, etc.
        pre_actions=[
            # Example: no-op JS that could configure the browser context
            # (real usage: await page.route(...) style via EvaluateJS or custom Action)
        ],
        actions=[
            Scroll(direction="down", px=500),
            Wait(ms=200),
            Scroll(direction="down", px=500),
        ],
        state=Selector("body"),
    )
    results = yoink.get_all([req])
    r = results[0]
    print(f"  ok={r.ok}  terminal={r.terminal}  {r.duration_ms}ms")


def scrape_with_click(url: str) -> None:
    """Click a 'load more' button before scraping, if it exists."""
    print(f"\nFetching with click: {url}")
    req = Request(
        url=url,
        actions=[
            Wait(ms=500),
            # EvaluateJS as a safe no-op click (won't throw if element absent)
            EvaluateJS("document.querySelector('h1') && document.querySelector('h1').click()"),
        ],
        state=Selector("h1"),
    )
    results = yoink.get_all([req])
    r = results[0]
    print(f"  ok={r.ok}  terminal={r.terminal}  {r.duration_ms}ms")


if __name__ == "__main__":
    # Use example.com as a safe public target for all demos
    target = "https://example.com"

    scrape_with_scroll(target)
    scrape_with_pre_actions(target)
    scrape_with_click(target)

    print("\nDone.")
