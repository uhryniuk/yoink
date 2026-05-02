"""Yoink — fast, fault-tolerant headless browser scraping."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from importlib.metadata import version as _version

from yoink.actions import (
    Action,
    Click,
    EvaluateJS,
    Fill,
    Hover,
    PressKey,
    RouteBlock,
    Scroll,
    ScrollToBottom,
    SelectOption,
    Wait,
    WaitForSelector,
)
from yoink.config import Config, load_config
from yoink.engine import Engine
from yoink.models import ProxyConfig, Request, Result
from yoink.states import (
    TICK_MS,
    All,
    Any,
    DOMContentLoaded,
    DOMStable,
    HTTPStatus,
    MinCount,
    NetworkIdle,
    Not,
    ResponseHeader,
    Selector,
    State,
    SubstringMatch,
    TimeDelay,
    URLMatches,
)

__version__: str = _version("python-yoink")

__all__ = [
    # Core
    "Engine",
    "Request",
    "Result",
    "ProxyConfig",
    "Config",
    "load_config",
    # Convenience functions
    "get",
    "get_all",
    "stream",
    # States
    "State",
    "All",
    "Any",
    "DOMContentLoaded",
    "DOMStable",
    "HTTPStatus",
    "MinCount",
    "NetworkIdle",
    "Not",
    "ResponseHeader",
    "Selector",
    "SubstringMatch",
    "TimeDelay",
    "URLMatches",
    "TICK_MS",
    # Actions
    "Action",
    "Click",
    "EvaluateJS",
    "Fill",
    "Hover",
    "PressKey",
    "RouteBlock",
    "Scroll",
    "ScrollToBottom",
    "SelectOption",
    "Wait",
    "WaitForSelector",
]


def get(url: str, state: State | None = None, retries: int = 0, tick_ms: int = TICK_MS, **kwargs) -> str:
    """Fetch a single URL and return its HTML.

    Uses sync-mode defaults: 1 worker, 1 page.

        html = yoink.get("https://example.com")
        html = yoink.get("https://example.com", state=Selector(".content"))
        html = yoink.get("https://example.com", retries=2, cookies={"s": "abc"})
    """
    req = Request(url=url, retries=retries, tick_ms=tick_ms, **kwargs)
    if state is not None:
        req.state = state
    cfg = load_config()
    cfg.workers.count = 1
    cfg.workers.page_limit = 1
    with Engine(cfg) as engine:
        engine.submit(req)
        return next(engine.results()).html


def get_all(
    urls: list[str | Request],
    workers: int | None = None,
    state: State | None = None,
    retries: int = 0,
    tick_ms: int = TICK_MS,
    **kwargs,
) -> list[Result]:
    """Fetch multiple URLs in parallel and return all results.

    Results are returned in completion order, not input order.
    Accepts a mix of URL strings and Request objects::

        results = yoink.get_all(["https://a.com", "https://b.com"], workers=4)
        results = yoink.get_all(
            [
                Request("https://a.com", state=Selector(".a")),
                Request("https://b.com", state=Selector(".b")),
            ]
        )
    """
    cfg = load_config()
    if workers is not None:
        cfg.workers.count = workers

    reqs = []
    for u in urls:
        if isinstance(u, Request):
            reqs.append(u)
        else:
            req = Request(url=u, retries=retries, tick_ms=tick_ms, **kwargs)
            if state is not None:
                req.state = state
            reqs.append(req)

    with Engine(cfg) as engine:
        return list(engine.stream(reqs))


def stream(
    urls: Iterable[str | Request],
    workers: int | None = None,
    state: State | None = None,
    retries: int = 0,
    tick_ms: int = TICK_MS,
    **kwargs,
) -> Iterator[Result]:
    """Fetch URLs and yield results as each completes.

    for result in yoink.stream(urls, workers=4, state=Selector(".data")):
        print(result.url, len(result.html))
    """
    cfg = load_config()
    if workers is not None:
        cfg.workers.count = workers
    with Engine(cfg) as engine:
        for u in urls:
            if isinstance(u, Request):
                engine.submit(u)
            else:
                req = Request(url=u, retries=retries, tick_ms=tick_ms, **kwargs)
                if state is not None:
                    req.state = state
                engine.submit(req)
        yield from engine.results()
