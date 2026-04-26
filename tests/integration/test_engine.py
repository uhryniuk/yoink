"""Integration tests for Engine — real Playwright against a local HTTP server."""

import pytest

import yoink
from yoink.engine import Engine
from yoink.models import Request
from yoink.states import DOMContentLoaded, HTTPStatus, Not, Selector, SubstringMatch


def test_engine_single_url(local_server, test_config):
    with Engine(test_config) as engine:
        engine.submit(local_server + "/")
        results = list(engine.results())

    assert len(results) == 1
    r = results[0]
    assert r.ok
    assert "Yoink Test Page" in r.html
    assert r.duration_ms > 0
    assert r.url.startswith("http://")


def test_engine_multiple_urls(local_server, test_config):
    urls = [local_server + "/" for _ in range(4)]
    with Engine(test_config) as engine:
        results = list(engine.stream(urls))

    assert len(results) == 4
    assert all(r.ok for r in results)


def test_engine_clean_html(local_server, test_config):
    req = Request(url=local_server + "/", clean_html=True)
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert "Yoink Test Page" in result.html
    assert "<script>" not in result.html
    assert "<style>" not in result.html


def test_engine_screenshot(local_server, test_config):
    req = Request(url=local_server + "/", screenshot=True)
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert result.screenshot is not None
    assert result.screenshot[:4] == b"\x89PNG"


def test_engine_error_returns_result_not_crash(test_config):
    """A bad URL should produce Result(ok=False), not raise."""
    req = Request(url="http://127.0.0.1:1/", timeout=3.0)
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert not result.ok
    assert result.error is not None


def test_engine_selector_state(local_server, test_config):
    """Selector state should resolve when #heading is in the DOM."""
    req = Request(url=local_server + "/")
    req.state = Selector("#heading")
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert "Yoink Test Page" in result.html


def test_result_has_http_metadata(local_server, test_config):
    """Result should carry status code and headers from the response."""
    with Engine(test_config) as engine:
        engine.submit(local_server + "/")
        result = next(engine.results())

    assert result.ok
    assert result.status == 200
    assert "content-type" in result.headers


def test_guard_passes(local_server, test_config):
    """Guard that matches should let the request through."""
    engine = Engine(test_config, guard=HTTPStatus(200))
    with engine:
        engine.submit(local_server + "/")
        result = next(engine.results())

    assert result.ok
    assert result.terminal == "success"


def test_guard_fails(local_server, test_config):
    """Guard that doesn't match should fail fast with guard_failed."""
    engine = Engine(test_config, guard=Not(SubstringMatch("Yoink Test Page")))
    with engine:
        engine.submit(local_server + "/")
        result = next(engine.results())

    assert not result.ok
    assert result.terminal == "guard_failed"


def test_middleware_state(local_server, test_config):
    """Middleware state should be AND'd into every request's state."""
    engine = Engine(test_config, middleware_state=DOMContentLoaded())
    with engine:
        req = Request(url=local_server + "/")
        req.state = Selector("#heading")
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert "Yoink Test Page" in result.html


def test_public_api_get(local_server, test_config):
    """yoink.get() one-liner works end to end."""
    original = yoink.load_config
    yoink.load_config = lambda *a, **kw: test_config
    try:
        html = yoink.get(local_server + "/")
        assert "Yoink Test Page" in html
    finally:
        yoink.load_config = original


def test_public_api_stream(local_server, test_config):
    """yoink.stream() yields results as they complete."""
    original = yoink.load_config
    yoink.load_config = lambda *a, **kw: test_config
    try:
        urls = [local_server + "/" for _ in range(3)]
        results = list(yoink.stream(urls))
        assert len(results) == 3
        assert all(r.ok for r in results)
    finally:
        yoink.load_config = original
