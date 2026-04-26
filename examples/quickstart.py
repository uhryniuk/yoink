"""Quickstart — covers the full yoink public API surface.

Run:
    uv run python examples/quickstart.py
"""

import sys

import yoink
from yoink import Engine, Request, Selector, NetworkIdle, HTTPStatus, load_config


def demo_get():
    print("=== yoink.get ===")
    html = yoink.get("https://example.com")
    print(f"  got {len(html)} bytes from example.com")


def demo_get_all():
    print("\n=== yoink.get_all ===")
    urls = [
        "https://example.com",
        "https://example.org",
    ]
    results = yoink.get_all(urls, workers=2)
    for r in results:
        status = "ok" if r.ok else f"FAIL({r.terminal})"
        print(f"  {r.url}  [{status}]  {len(r.html)} bytes")


def demo_stream():
    print("\n=== yoink.stream ===")
    urls = ["https://example.com", "https://example.org"]
    for result in yoink.stream(urls):
        print(f"  streamed: {result.url}  {result.duration_ms}ms")


def demo_engine_with_guard():
    print("\n=== Engine with guard ===")
    cfg = load_config()
    cfg.workers.count = 1
    cfg.workers.page_limit = 1

    # Guard: reject any page that returns a non-2xx status
    guard = HTTPStatus(lambda s: 200 <= s < 300)

    with Engine(cfg, guard=guard) as engine:
        engine.submit(Request(url="https://example.com"))
        for result in engine.results():
            print(f"  {result.url}  terminal={result.terminal}")


def demo_engine_with_middleware_state():
    print("\n=== Engine with middleware_state ===")
    cfg = load_config()
    cfg.workers.count = 1
    cfg.workers.page_limit = 1

    # middleware_state is AND'd into every request automatically
    middleware = NetworkIdle()

    reqs = [
        Request(url="https://example.com", state=Selector("h1")),
        Request(url="https://example.org", state=Selector("h1")),
    ]

    with Engine(cfg, middleware_state=middleware) as engine:
        for req in reqs:
            engine.submit(req)
        for result in engine.results():
            print(f"  {result.url}  ok={result.ok}  {result.duration_ms}ms")


def demo_request_options():
    print("\n=== Request options ===")
    req = Request(
        url="https://example.com",
        state=Selector("h1"),
        tick_ms=100,
        retries=2,
        timeout=15.0,
        clean_html=True,
        headers={"X-Scraper": "yoink"},
    )
    result = yoink.get_all([req])[0]
    print(f"  ok={result.ok}  terminal={result.terminal}  {result.duration_ms}ms")


if __name__ == "__main__":
    demo_get()
    demo_get_all()
    demo_stream()
    demo_engine_with_guard()
    demo_engine_with_middleware_state()
    demo_request_options()
    print("\nDone.")
