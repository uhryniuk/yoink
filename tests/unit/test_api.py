"""Unit tests for the top-level convenience API (get, get_all, stream)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import yoink
from yoink import Request, Selector
from yoink.models import Result
from yoink.states import TICK_MS


def _make_result(url: str, **kwargs) -> Result:
    req = Request(url=url)
    return Result(request=req, url=url, html="<html/>", terminal="success", **kwargs)


class TestGet:
    def test_retries_forwarded_to_request(self):
        result = _make_result("https://example.com")
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def submit(self, req):
                captured.append(req)

            def results(self):
                yield result

        with patch("yoink.Engine", FakeEngine):
            yoink.get("https://example.com", retries=3)

        assert len(captured) == 1
        assert captured[0].retries == 3

    def test_tick_ms_forwarded_to_request(self):
        result = _make_result("https://example.com")
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw):
                pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, req): captured.append(req)
            def results(self): yield result

        with patch("yoink.Engine", FakeEngine):
            yoink.get("https://example.com", tick_ms=50)

        assert captured[0].tick_ms == 50

    def test_state_forwarded_to_request(self):
        result = _make_result("https://example.com")
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, req): captured.append(req)
            def results(self): yield result

        s = Selector(".x")
        with patch("yoink.Engine", FakeEngine):
            yoink.get("https://example.com", state=s)

        assert captured[0].state is s

    def test_kwargs_forwarded_to_request(self):
        result = _make_result("https://example.com")
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, req): captured.append(req)
            def results(self): yield result

        with patch("yoink.Engine", FakeEngine):
            yoink.get("https://example.com", cookies={"s": "abc"}, clean_html=True)

        req = captured[0]
        assert req.cookies == {"s": "abc"}
        assert req.clean_html is True


class TestGetAll:
    def test_retries_forwarded_for_url_strings(self):
        results_list = [_make_result("https://a.com"), _make_result("https://b.com")]
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def stream(self, reqs):
                captured.extend(reqs)
                return iter(results_list)

        with patch("yoink.Engine", FakeEngine):
            yoink.get_all(["https://a.com", "https://b.com"], retries=2)

        assert all(r.retries == 2 for r in captured)

    def test_request_objects_passed_through_unchanged(self):
        req_a = Request(url="https://a.com", retries=5, tick_ms=100)
        req_b = Request(url="https://b.com", retries=0)
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def stream(self, reqs):
                captured.extend(reqs)
                return iter([_make_result(r.url) for r in reqs])

        with patch("yoink.Engine", FakeEngine):
            yoink.get_all([req_a, req_b], retries=99)  # retries=99 should NOT override req objects

        assert captured[0].retries == 5   # req_a unchanged
        assert captured[1].retries == 0   # req_b unchanged

    def test_tick_ms_default(self):
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def stream(self, reqs):
                captured.extend(reqs)
                return iter([_make_result(r.url) for r in reqs])

        with patch("yoink.Engine", FakeEngine):
            yoink.get_all(["https://x.com"])

        assert captured[0].tick_ms == TICK_MS


class TestStream:
    def test_retries_forwarded_for_url_strings(self):
        captured = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, req): captured.append(req)
            def results(self):
                return iter([_make_result(r.url) for r in captured])

        with patch("yoink.Engine", FakeEngine):
            list(yoink.stream(["https://x.com"], retries=1))

        assert captured[0].retries == 1

    def test_request_objects_passed_through(self):
        req = Request(url="https://x.com", retries=7)
        submitted = []

        class FakeEngine:
            def __init__(self, cfg, **kw): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def submit(self, r): submitted.append(r)
            def results(self): return iter([_make_result("https://x.com")])

        with patch("yoink.Engine", FakeEngine):
            list(yoink.stream([req], retries=99))

        assert submitted[0] is req  # same object, not a copy
        assert submitted[0].retries == 7  # unchanged
