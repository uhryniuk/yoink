"""Unit tests for worker retry logic."""

from __future__ import annotations

import asyncio
from multiprocessing import Queue
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yoink.config import WorkerConfig
from yoink.models import Request, Result
from yoink.rate_limiter import RateLimiter
from yoink.worker import _fetch


def make_config(**kwargs) -> WorkerConfig:
    defaults = dict(count=1, page_limit=1, idle_timeout_secs=30, headless=True, user_agent=None)
    defaults.update(kwargs)
    return WorkerConfig(**defaults)


def make_rate_limiter() -> RateLimiter:
    rl = MagicMock(spec=RateLimiter)
    rl.acquire = AsyncMock()
    return rl


class TestRetries:
    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        """Successful result is returned immediately, no retry."""
        req = Request(url="https://example.com", retries=2)
        success = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=success) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert mock.call_count == 1
        result = output_q.get(timeout=2.0)
        assert result.terminal == "success"

    @pytest.mark.asyncio
    async def test_retries_on_error_terminal(self):
        """A result with terminal='error' is retried up to req.retries times."""
        req = Request(url="https://example.com", retries=2)
        error_result = Result(request=req, url=req.url, html="", terminal="error", error=RuntimeError("boom"))
        success_result = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch(
            "yoink.worker._fetch_once", new_callable=AsyncMock, side_effect=[error_result, success_result]
        ) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert mock.call_count == 2
        result = output_q.get(timeout=2.0)
        assert result.terminal == "success"

    @pytest.mark.asyncio
    async def test_retries_on_timeout_terminal(self):
        """A result with terminal='timeout' is retried."""
        req = Request(url="https://example.com", retries=1)
        timeout_result = Result(request=req, url=req.url, html="", terminal="timeout")
        success_result = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch(
            "yoink.worker._fetch_once", new_callable=AsyncMock, side_effect=[timeout_result, success_result]
        ) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert mock.call_count == 2
        result = output_q.get(timeout=2.0)
        assert result.terminal == "success"

    @pytest.mark.asyncio
    async def test_exhausts_retries_returns_last_result(self):
        """When all attempts fail, the last failure result is returned."""
        req = Request(url="https://example.com", retries=2)
        error_result = Result(request=req, url=req.url, html="", terminal="error", error=RuntimeError("always fails"))

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=error_result) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        # 1 initial + 2 retries = 3 total
        assert mock.call_count == 3
        result = output_q.get(timeout=2.0)
        assert result.terminal == "error"

    @pytest.mark.asyncio
    async def test_no_retry_on_guard_failed(self):
        """guard_failed is a terminal decision — not retried."""
        req = Request(url="https://example.com", retries=3)
        guard_result = Result(request=req, url=req.url, html="", terminal="guard_failed")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=guard_result) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert mock.call_count == 1
        result = output_q.get(timeout=2.0)
        assert result.terminal == "guard_failed"

    @pytest.mark.asyncio
    async def test_zero_retries_is_single_attempt(self):
        """retries=0 means exactly one attempt."""
        req = Request(url="https://example.com", retries=0)
        error_result = Result(request=req, url=req.url, html="", terminal="error", error=RuntimeError("fail"))

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=error_result) as mock:
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_exception_retried(self):
        """Bare exceptions from _fetch_once are caught and retried."""
        req = Request(url="https://example.com", retries=1)
        success_result = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        call_count = 0

        async def fetch_once_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("network blip")
            return success_result

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, side_effect=fetch_once_side_effect):
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        assert call_count == 2
        result = output_q.get(timeout=2.0)
        assert result.terminal == "success"

    @pytest.mark.asyncio
    async def test_duration_covers_all_attempts(self):
        """duration_ms reflects total time including all retries."""
        req = Request(url="https://example.com", retries=1)
        error_result = Result(request=req, url=req.url, html="", terminal="error", error=RuntimeError("x"))

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(0.02)  # 20ms per attempt
            return error_result

        with patch("yoink.worker._fetch_once", new_callable=AsyncMock, side_effect=slow_fetch):
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        result = output_q.get(timeout=2.0)
        # 2 attempts × ~20ms each → duration should be ≥ 40ms
        assert result.duration_ms >= 30


# ---------------------------------------------------------------------------
# httpx fast path (_httpx_fetch)
# ---------------------------------------------------------------------------


class TestHttpxFetch:
    """Tests for _httpx_fetch — patches httpx.AsyncClient to avoid network calls."""

    def _make_mock_response(self, text="<html/>", status=200, url="https://example.com/"):
        resp = MagicMock()
        resp.text = text
        resp.status_code = status
        resp.url = url
        resp.headers = {"content-type": "text/html"}
        return resp

    @pytest.mark.asyncio
    async def test_success_returns_result(self):
        from yoink.worker import _httpx_fetch

        req = Request(url="https://example.com", use_browser=False)
        rl = make_rate_limiter()
        mock_resp = self._make_mock_response(text="<html><body>hi</body></html>", status=200)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("yoink.worker._httpx.AsyncClient", return_value=mock_client):
            result = await _httpx_fetch(req, rl)

        assert result.ok
        assert result.status == 200
        assert result.terminal == "success"
        assert result.html == "<html><body>hi</body></html>"
        rl.acquire.assert_awaited_once_with(req.url)

    @pytest.mark.asyncio
    async def test_cookies_sent_as_header(self):
        from yoink.worker import _httpx_fetch

        req = Request(url="https://example.com", use_browser=False, cookies={"sid": "abc", "x": "1"})
        rl = make_rate_limiter()
        mock_resp = self._make_mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("yoink.worker._httpx.AsyncClient", return_value=mock_client):
            await _httpx_fetch(req, rl)

        call_kwargs = mock_client.get.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "Cookie" in headers
        assert "sid=abc" in headers["Cookie"]
        assert "x=1" in headers["Cookie"]

    @pytest.mark.asyncio
    async def test_existing_cookie_header_not_overwritten(self):
        from yoink.worker import _httpx_fetch

        req = Request(
            url="https://example.com",
            use_browser=False,
            headers={"Cookie": "manual=yes"},
            cookies={"auto": "no"},
        )
        rl = make_rate_limiter()
        mock_resp = self._make_mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("yoink.worker._httpx.AsyncClient", return_value=mock_client):
            await _httpx_fetch(req, rl)

        call_kwargs = mock_client.get.call_args[1]
        headers = call_kwargs.get("headers", {})
        # Manual header wins via setdefault
        assert headers["Cookie"] == "manual=yes"

    @pytest.mark.asyncio
    async def test_proxy_passed_to_client(self):
        from yoink.models import ProxyConfig
        from yoink.worker import _httpx_fetch

        req = Request(
            url="https://example.com",
            use_browser=False,
            proxy=ProxyConfig(server="http://proxy:8080"),
        )
        rl = make_rate_limiter()
        mock_resp = self._make_mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        captured = {}

        def capture_client(**kwargs):
            captured.update(kwargs)
            return mock_client

        with patch("yoink.worker._httpx.AsyncClient", side_effect=capture_client):
            await _httpx_fetch(req, rl)

        assert captured["proxy"] == "http://proxy:8080"

    @pytest.mark.asyncio
    async def test_no_proxy_passes_none(self):
        from yoink.worker import _httpx_fetch

        req = Request(url="https://example.com", use_browser=False)
        rl = make_rate_limiter()
        mock_resp = self._make_mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        captured = {}

        def capture_client(**kwargs):
            captured.update(kwargs)
            return mock_client

        with patch("yoink.worker._httpx.AsyncClient", side_effect=capture_client):
            await _httpx_fetch(req, rl)

        assert captured["proxy"] is None


class TestUseBrowserRouting:
    """_fetch routes to httpx when use_browser=False and httpx is available."""

    @pytest.mark.asyncio
    async def test_use_browser_false_calls_httpx_fetch(self):
        req = Request(url="https://example.com", retries=0, use_browser=False)
        success = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with (
            patch("yoink.worker._HTTPX_AVAILABLE", True),
            patch("yoink.worker._httpx_fetch", new_callable=AsyncMock, return_value=success) as mock_httpx,
            patch("yoink.worker._fetch_once", new_callable=AsyncMock) as mock_browser,
        ):
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        mock_httpx.assert_awaited_once()
        mock_browser.assert_not_awaited()
        result = output_q.get(timeout=2.0)
        assert result.terminal == "success"

    @pytest.mark.asyncio
    async def test_use_browser_true_calls_browser_fetch(self):
        req = Request(url="https://example.com", retries=0, use_browser=True)
        success = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with (
            patch("yoink.worker._HTTPX_AVAILABLE", True),
            patch("yoink.worker._httpx_fetch", new_callable=AsyncMock) as mock_httpx,
            patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=success) as mock_browser,
        ):
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        mock_httpx.assert_not_awaited()
        mock_browser.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_use_browser_false_falls_back_when_httpx_unavailable(self):
        req = Request(url="https://example.com", retries=0, use_browser=False)
        success = Result(request=req, url=req.url, html="<html/>", terminal="success")

        output_q = Queue()
        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()

        with (
            patch("yoink.worker._HTTPX_AVAILABLE", False),
            patch("yoink.worker._httpx_fetch", new_callable=AsyncMock) as mock_httpx,
            patch("yoink.worker._fetch_once", new_callable=AsyncMock, return_value=success) as mock_browser,
        ):
            await _fetch(
                browser=MagicMock(),
                req=req,
                output_q=output_q,
                rate_limiter=make_rate_limiter(),
                semaphore=semaphore,
                config=make_config(),
            )

        mock_httpx.assert_not_awaited()
        mock_browser.assert_awaited_once()
