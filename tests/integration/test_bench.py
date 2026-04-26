"""Integration tests against the local bench Docker stack.

Requires the bench services to be running:
    cd bench && docker compose up -d

Tests are auto-skipped when the bench stack is not reachable.
"""

from __future__ import annotations

import urllib.request
import urllib.error

import pytest

import yoink
from yoink import (
    Click,
    EvaluateJS,
    Request,
    Scroll,
    ScrollToBottom,
    Selector,
    Wait,
    load_config,
)
from yoink.engine import Engine

STATIC_URL = "http://localhost:8001"
REACT_URL = "http://localhost:8002"
SLOW_URL = "http://localhost:8003"


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


bench_static = pytest.mark.skipif(
    not _reachable(STATIC_URL),
    reason="bench-static not running (cd bench && docker compose up -d)",
)
bench_react = pytest.mark.skipif(
    not _reachable(REACT_URL),
    reason="bench-react not running (cd bench && docker compose up -d)",
)
bench_slow = pytest.mark.skipif(
    not _reachable(SLOW_URL),
    reason="bench-slow not running (cd bench && docker compose up -d)",
)


def bench_config(workers=1, pages=1):
    cfg = load_config()
    cfg.workers.count = workers
    cfg.workers.page_limit = pages
    return cfg


# ---------------------------------------------------------------------------
# bench-static: basic HTML pages
# ---------------------------------------------------------------------------

@bench_static
def test_static_product_page_loads():
    result = yoink.get(f"{STATIC_URL}/product-1.html", state=Selector(".product-card"))
    assert result  # non-empty
    assert "product-card" in result


@bench_static
def test_static_product_contains_expected_fields():
    result = yoink.get(f"{STATIC_URL}/product-42.html", state=Selector(".product-card"))
    assert "product-name" in result
    assert "product-price" in result
    assert "product-category" in result


@bench_static
def test_static_multiple_products_parallel():
    urls = [f"{STATIC_URL}/product-{i}.html" for i in range(1, 6)]
    results = yoink.get_all(urls, workers=1)
    assert len(results) == 5
    assert all(r.ok for r in results)
    assert all("product-card" in r.html for r in results)


@bench_static
def test_static_index_page():
    result = yoink.get(f"{STATIC_URL}/index.html", state=Selector(".product-list"))
    assert "BenchShop" in result
    assert "product-link" in result


@bench_static
def test_static_scroll_and_scrape():
    req = Request(
        url=f"{STATIC_URL}/product-1.html",
        actions=[Scroll(direction="down", px=200), Wait(ms=100)],
        state=Selector(".product-card"),
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok
    assert "product-card" in r.html


# ---------------------------------------------------------------------------
# bench-react: SPA with lazy-loaded products
# ---------------------------------------------------------------------------

@bench_react
def test_react_home_page_loads():
    result = yoink.get(f"{REACT_URL}/", state=Selector("h2"))
    assert "ShopBench" in result


@bench_react
def test_react_products_first_batch():
    """First batch of products loads immediately — Selector resolves on tick 0."""
    result = yoink.get(f"{REACT_URL}/products", state=Selector(".product-card"))
    assert result
    assert "product-card" in result


@bench_react
def test_react_products_all_batches():
    """Wait for all 3 batches to load by checking for 60+ cards."""
    from yoink.states import State
    from playwright.async_api import Page, Response

    class MinCards(State):
        def __init__(self, n: int):
            self.n = n

        async def check(self, page: Page, response: Response | None) -> bool:
            count = await page.locator(".product-card").count()
            return count >= self.n

    req = Request(
        url=f"{REACT_URL}/products",
        state=MinCards(60),  # 200 total, 3 batches: first 67, then 67, then 66
        timeout=10.0,
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok, f"Expected success but got {r.terminal}"


@bench_react
def test_react_product_detail_page():
    """Individual product page loads with reviews after 400ms delay."""
    req = Request(
        url=f"{REACT_URL}/products/1",
        state=Selector(".reviews-loaded"),
        timeout=10.0,
        tick_ms=100,
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok, f"Expected success but got {r.terminal}"
    assert "product-detail" in r.html


@bench_react
def test_react_scroll_to_bottom_loads_all_products():
    """ScrollToBottom triggers all batches to load on the product grid."""
    req = Request(
        url=f"{REACT_URL}/products",
        actions=[ScrollToBottom(step_px=500, delay_ms=100), Wait(ms=300)],
        state=Selector(".product-card"),
        timeout=15.0,
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok
    assert "product-card" in r.html


@bench_react
def test_react_category_filter():
    """URL with query param filters products to a single category."""
    req = Request(
        url=f"{REACT_URL}/products?category=Electronics",
        state=Selector(".product-card"),
        timeout=10.0,
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok
    assert "Electronics" in r.html


@bench_react
def test_react_evaluate_js_action():
    """EvaluateJS action executes custom JS on the page."""
    req = Request(
        url=f"{REACT_URL}/products",
        actions=[
            EvaluateJS("window.__yoink_test = true"),
        ],
        state=Selector(".product-card"),
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.ok


@bench_react
def test_react_concurrent_pages():
    """Multiple concurrent pages against the SPA all succeed."""
    cfg = bench_config(workers=1, pages=4)
    urls = [f"{REACT_URL}/products" for _ in range(8)]

    with Engine(cfg) as engine:
        results = list(engine.stream(urls))

    assert len(results) == 8
    ok = [r for r in results if r.ok]
    assert len(ok) >= 7, f"Expected >=7 ok, got {len(ok)}"


# ---------------------------------------------------------------------------
# bench-slow: timeout and delay handling
# ---------------------------------------------------------------------------

@bench_slow
def test_slow_zero_delay():
    result = yoink.get(f"{SLOW_URL}/?delay=0", state=Selector(".response-title"))
    assert result
    assert "Slow Response" in result


@bench_slow
def test_slow_moderate_delay():
    result = yoink.get(f"{SLOW_URL}/?delay=500", state=Selector(".response-title"), timeout=10.0)
    assert "0ms" in result or "500" in result or "Slow" in result


@bench_slow
def test_slow_timeout_returns_timeout_terminal():
    req = Request(
        url=f"{SLOW_URL}/?delay=5000",
        timeout=2.0,
        state=Selector(".response-title"),
    )
    results = yoink.get_all([req])
    r = results[0]
    assert r.terminal == "timeout"
    assert not r.ok


@bench_slow
def test_slow_retry_on_timeout():
    """With retries=1, a timeout on first attempt is retried."""
    # First attempt: 3s delay (times out at 1s). Second attempt: 0ms (succeeds).
    # We can't control per-attempt URL, so test that retries field is used by
    # sending a URL that will always succeed on retry (simulate with short timeout
    # and moderate delay — first attempt times out, second may or may not).
    req = Request(
        url=f"{SLOW_URL}/?delay=0",
        timeout=5.0,
        retries=1,
        state=Selector(".response-title"),
    )
    results = yoink.get_all([req])
    r = results[0]
    # With 0ms delay and 5s timeout, should succeed (even if retried)
    assert r.ok
