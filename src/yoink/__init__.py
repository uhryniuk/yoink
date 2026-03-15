"""Yoink — fast, fault-tolerant headless browser scraping."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from yoink.config import Config, load_config
from yoink.engine import Engine
from yoink.models import Action, ExtractReq, ExtractResult, ProxyConfig, RetryPolicy

__version__ = "0.1.1"

__all__ = [
    "Engine",
    "ExtractReq",
    "ExtractResult",
    "RetryPolicy",
    "ProxyConfig",
    "Action",
    "Config",
    "load_config",
    "get",
    "get_all",
    "stream",
]


def get(url: str, **kwargs) -> str:
    """Fetch a single URL and return its HTML.

    Keyword arguments are forwarded to :class:`ExtractReq`::

        html = yoink.get("https://example.com", screenshot=False, clean_html=True)
    """
    req = ExtractReq(url=url, **kwargs)
    cfg = load_config()
    cfg.workers.count = 1
    with Engine(cfg) as engine:
        engine.submit(req)
        return next(engine.results()).html


def get_all(urls: list[str], workers: int | None = None, **kwargs) -> list[ExtractResult]:
    """Fetch multiple URLs in parallel and return all results.

    Results are returned in completion order, not input order::

        results = yoink.get_all(["https://a.com", "https://b.com"], workers=4)
        for r in results:
            print(r.url, r.ok)
    """
    cfg = load_config()
    if workers is not None:
        cfg.workers.count = workers
    reqs = [ExtractReq(url=u, **kwargs) for u in urls]
    with Engine(cfg) as engine:
        return list(engine.stream(reqs))


def stream(
    urls: Iterable[str],
    workers: int | None = None,
    **kwargs,
) -> Iterator[ExtractResult]:
    """Fetch URLs and yield results as each completes.

    Keeps the Engine alive for the duration of iteration::

        for result in yoink.stream(urls, workers=4, clean_html=True):
            print(result.url, len(result.html))
    """
    cfg = load_config()
    if workers is not None:
        cfg.workers.count = workers
    reqs = [ExtractReq(url=u, **kwargs) for u in urls]
    with Engine(cfg) as engine:
        yield from engine.stream(reqs)
