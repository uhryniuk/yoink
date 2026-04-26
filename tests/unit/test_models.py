"""Unit tests for models.py."""

import json

import pytest

from yoink.models import Action, ProxyConfig, Request, Result, RetryPolicy


class TestRetryPolicy:
    def test_defaults(self):
        r = RetryPolicy()
        assert r.max_attempts == 3
        assert r.backoff_factor == 2.0
        assert r.retry_on_scraper_error is True

    def test_custom(self):
        r = RetryPolicy(max_attempts=1, backoff_factor=0.5)
        assert r.max_attempts == 1


class TestProxyConfig:
    def test_required_server(self):
        p = ProxyConfig(server="http://proxy:8080")
        assert p.server == "http://proxy:8080"
        assert p.username is None
        assert p.password is None

    def test_with_credentials(self):
        p = ProxyConfig(server="http://proxy:8080", username="u", password="p")
        assert p.username == "u"


class TestAction:
    def test_click(self):
        a = Action(type="click", selector="//button")
        assert a.type == "click"
        assert a.selector == "//button"
        assert a.value is None
        assert a.duration_ms is None

    def test_wait(self):
        a = Action(type="wait", duration_ms=500)
        assert a.duration_ms == 500


class TestRequest:
    def test_defaults(self):
        req = Request(url="https://example.com")
        assert req.timeout == 30.0
        assert req.screenshot is False
        assert req.clean_html is False
        assert req.headers == {}
        assert req.metadata == {}
        assert req.proxy is None

    def test_json_roundtrip_minimal(self):
        req = Request(url="https://example.com")
        restored = Request.from_json(req.to_json())
        assert restored.url == req.url
        assert restored.timeout == req.timeout

    def test_json_roundtrip_full(self):
        req = Request(
            url="https://example.com",
            proxy=ProxyConfig(server="http://p:8080", username="u", password="pw"),
            headers={"X-Custom": "value"},
            metadata={"job_id": "abc123"},
            screenshot=True,
            clean_html=True,
        )
        restored = Request.from_json(req.to_json())
        assert restored.proxy.server == "http://p:8080"
        assert restored.proxy.username == "u"
        assert restored.headers == {"X-Custom": "value"}
        assert restored.metadata["job_id"] == "abc123"
        assert restored.screenshot is True
        assert restored.clean_html is True

    def test_from_dict_does_not_mutate_input(self):
        data = {
            "url": "https://x.com",
            "proxy": {"server": "http://p:8080"},
            "metadata": {"_request_id": "xyz"},
        }
        original_proxy = data["proxy"]
        Request.from_dict(data)
        # The caller's dict should be untouched
        assert "proxy" in data
        assert data["proxy"] is original_proxy


class TestResult:
    def test_ok_on_success(self):
        req = Request(url="https://example.com")
        r = Result(request=req, url="https://example.com", html="<html/>")
        assert r.ok is True
        assert r.terminal == "success"
        assert r.error is None

    def test_ok_false_on_timeout(self):
        req = Request(url="https://example.com")
        r = Result(request=req, url="https://example.com", html="", terminal="timeout")
        assert r.ok is False

    def test_ok_false_on_error(self):
        req = Request(url="https://example.com")
        r = Result(
            request=req, url="https://example.com", html="",
            terminal="error", error=RuntimeError("boom"),
        )
        assert r.ok is False

    def test_to_dict_keys(self):
        req = Request(url="https://example.com")
        r = Result(request=req, url="https://example.com", html="<p>hi</p>", duration_ms=42)
        d = r.to_dict()
        assert set(d.keys()) == {
            "url", "html", "status", "headers", "screenshot",
            "duration_ms", "terminal", "ok", "error", "request",
        }
        assert d["ok"] is True
        assert d["duration_ms"] == 42
        assert d["screenshot"] is None
        assert d["terminal"] == "success"

    def test_to_json_is_valid(self):
        req = Request(url="https://example.com")
        r = Result(request=req, url="https://example.com", html="<p/>")
        parsed = json.loads(r.to_json())
        assert parsed["url"] == "https://example.com"

    def test_screenshot_hex_in_dict(self):
        req = Request(url="https://example.com")
        r = Result(request=req, url="https://example.com", html="", screenshot=b"\x89PNG")
        assert r.to_dict()["screenshot"] == b"\x89PNG".hex()
