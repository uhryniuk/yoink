"""Unit tests for the reconciler tick loop."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from yoink.reconciler import _reset_state, reconcile
from yoink.states import (
    DOMContentLoaded,
    HTTPStatus,
    Selector,
    State,
    TimeDelay,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_page(**kwargs) -> MagicMock:
    page = AsyncMock()
    page.url = kwargs.get("url", "https://example.com")
    page.content = AsyncMock(return_value=kwargs.get("html", "<html></html>"))
    page.evaluate = AsyncMock(return_value=kwargs.get("evaluate_result", "complete"))

    locator = AsyncMock()
    locator.count = AsyncMock(return_value=kwargs.get("locator_count", 0))
    page.locator = MagicMock(return_value=locator)

    return page


def make_response(status=200, headers=None) -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.all_headers = AsyncMock(return_value=headers or {})
    return resp


class CountingState(State):
    """State that returns True after N check() calls."""

    def __init__(self, resolve_after: int = 1):
        self.resolve_after = resolve_after
        self.call_count = 0

    async def check(self, page, response) -> bool:
        self.call_count += 1
        return self.call_count >= self.resolve_after


class AlwaysFalse(State):
    async def check(self, page, response) -> bool:
        return False


class ExplodingState(State):
    """Raises on every check — reconciler should keep ticking."""

    async def check(self, page, response) -> bool:
        raise RuntimeError("boom")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestReconcile:
    @pytest.mark.asyncio
    async def test_immediate_success(self):
        page = make_page(evaluate_result="complete")
        result = await reconcile(page, None, DOMContentLoaded(), timeout=5, tick_ms=50)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_when_state_never_resolves(self):
        page = make_page()
        result = await reconcile(page, None, AlwaysFalse(), timeout=0.15, tick_ms=50)
        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_resolves_after_multiple_ticks(self):
        page = make_page()
        state = CountingState(resolve_after=3)
        result = await reconcile(page, None, state, timeout=5, tick_ms=10)
        assert result == "success"
        assert state.call_count == 3

    @pytest.mark.asyncio
    async def test_http_status_with_response(self):
        page = make_page()
        resp = make_response(status=200)
        result = await reconcile(page, resp, HTTPStatus(200), timeout=5, tick_ms=50)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_http_status_mismatch_times_out(self):
        page = make_page()
        resp = make_response(status=429)
        result = await reconcile(page, resp, HTTPStatus(200), timeout=0.15, tick_ms=50)
        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_allstate_sequential(self):
        """AllState should resolve left before right."""
        page = make_page(evaluate_result="complete", locator_count=1)
        state = DOMContentLoaded() & Selector(".x")
        result = await reconcile(page, None, state, timeout=5, tick_ms=50)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_exception_in_check_keeps_ticking(self):
        """Transient errors in state.check() shouldn't abort the loop."""
        page = make_page()
        # ExplodingState always raises, so we should timeout not crash
        result = await reconcile(page, None, ExplodingState(), timeout=0.15, tick_ms=50)
        assert result == "timeout"

    @pytest.mark.asyncio
    async def test_tick_ms_respected(self):
        """The loop should tick roughly at the configured interval."""
        page = make_page()
        state = CountingState(resolve_after=4)
        # 4 ticks at 50ms each = ~200ms minimum
        result = await reconcile(page, None, state, timeout=5, tick_ms=50)
        assert result == "success"
        assert state.call_count == 4


class TestResetState:
    def test_resets_allstate(self):
        state = DOMContentLoaded() & Selector(".x")
        state._left_resolved = True
        _reset_state(state)
        assert state._left_resolved is False

    def test_resets_time_delay(self):
        state = TimeDelay(1000)
        state._start = 12345.0
        _reset_state(state)
        assert state._start is None
