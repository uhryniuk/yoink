"""Integration tests for Engine — real Playwright against a local HTTP server."""

import pytest

import yoink
from yoink.engine import Engine
from yoink.models import ExtractReq, RetryPolicy


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
    req = ExtractReq(url=local_server + "/", clean_html=True)
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert "Yoink Test Page" in result.html
    assert "<script>" not in result.html
    assert "<style>" not in result.html


def test_engine_screenshot(local_server, test_config):
    req = ExtractReq(url=local_server + "/", screenshot=True)
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert result.screenshot is not None
    assert result.screenshot[:4] == b"\x89PNG"


def test_engine_error_returns_result_not_crash(test_config):
    """A bad URL should produce ExtractResult(ok=False), not raise."""
    req = ExtractReq(
        url="http://127.0.0.1:1/",  # nothing listening
        timeout=3.0,
        retry=RetryPolicy(max_attempts=1),
    )
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert not result.ok
    assert result.error is not None


def test_engine_css_selector_wait(local_server, test_config):
    req = ExtractReq(url=local_server + "/", wait_for="#heading")
    with Engine(test_config) as engine:
        engine.submit(req)
        result = next(engine.results())

    assert result.ok
    assert "Yoink Test Page" in result.html


def test_public_api_get(local_server, test_config):
    """yoink.get() one-liner works end to end."""
    import yoink
    # Patch load_config so this test uses the test config
    original = yoink.load_config
    yoink.load_config = lambda *a, **kw: test_config
    try:
        html = yoink.get(local_server + "/")
        assert "Yoink Test Page" in html
    finally:
        yoink.load_config = original


def test_public_api_stream(local_server, test_config):
    """yoink.stream() yields results as they complete."""
    import yoink
    original = yoink.load_config
    yoink.load_config = lambda *a, **kw: test_config
    try:
        urls = [local_server + "/" for _ in range(3)]
        results = list(yoink.stream(urls))
        assert len(results) == 3
        assert all(r.ok for r in results)
    finally:
        yoink.load_config = original
