"""Unit tests for the State composition system."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from yoink.states import (
    AllState,
    AnyState,
    DOMContentLoaded,
    DOMStable,
    HTTPStatus,
    NetworkIdle,
    Not,
    ResponseHeader,
    Selector,
    State,
    SubstringMatch,
    TimeDelay,
    URLMatches,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_page(**kwargs) -> MagicMock:
    """Build a mock Page with sensible defaults."""
    page = AsyncMock()
    page.url = kwargs.get("url", "https://example.com")
    page.content = AsyncMock(return_value=kwargs.get("html", "<html></html>"))
    page.evaluate = AsyncMock(return_value=kwargs.get("evaluate_result", "complete"))
    page.inner_text = AsyncMock(return_value=kwargs.get("inner_text", ""))

    locator = AsyncMock()
    locator.count = AsyncMock(return_value=kwargs.get("locator_count", 0))
    page.locator = MagicMock(return_value=locator)

    return page


def make_response(status=200, headers=None) -> AsyncMock:
    resp = AsyncMock()
    resp.status = status
    resp.all_headers = AsyncMock(return_value=headers or {})
    return resp


# ---------------------------------------------------------------------------
# Operator composition
# ---------------------------------------------------------------------------


class TestOperators:
    def test_and_returns_all_state(self):
        a = DOMContentLoaded()
        b = Selector(".x")
        result = a & b
        assert isinstance(result, AllState)

    def test_or_returns_any_state(self):
        a = DOMContentLoaded()
        b = Selector(".x")
        result = a | b
        assert isinstance(result, AnyState)

    def test_invert_returns_not(self):
        s = DOMContentLoaded()
        result = ~s
        assert isinstance(result, Not)

    def test_chaining(self):
        """(A & B) | C should produce AnyState(AllState(A, B), C)."""
        a, b, c = DOMContentLoaded(), Selector(".x"), TimeDelay(100)
        result = (a & b) | c
        assert isinstance(result, AnyState)
        assert isinstance(result.left, AllState)


# ---------------------------------------------------------------------------
# AllState (sequential AND)
# ---------------------------------------------------------------------------


class TestAllState:
    @pytest.mark.asyncio
    async def test_both_true(self):
        page = make_page(evaluate_result="complete", locator_count=1)
        state = DOMContentLoaded() & Selector(".x")
        assert await state.check(page, None) is True

    @pytest.mark.asyncio
    async def test_left_false_blocks_right(self):
        page = make_page(evaluate_result="loading", locator_count=1)
        state = DOMContentLoaded() & Selector(".x")
        assert await state.check(page, None) is False
        # locator should not have been called since left didn't resolve
        page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_left_true_right_false(self):
        page = make_page(evaluate_result="complete", locator_count=0)
        state = DOMContentLoaded() & Selector(".x")
        assert await state.check(page, None) is False

    @pytest.mark.asyncio
    async def test_reset_clears_left_resolved(self):
        page = make_page(evaluate_result="complete", locator_count=1)
        state = DOMContentLoaded() & Selector(".x")
        await state.check(page, None)
        assert state._left_resolved is True
        state.reset()
        assert state._left_resolved is False


# ---------------------------------------------------------------------------
# AnyState (concurrent OR)
# ---------------------------------------------------------------------------


class TestAnyState:
    @pytest.mark.asyncio
    async def test_left_true(self):
        page = make_page(evaluate_result="complete")
        state = DOMContentLoaded() | Selector(".x")
        assert await state.check(page, None) is True

    @pytest.mark.asyncio
    async def test_right_true(self):
        page = make_page(evaluate_result="loading", locator_count=1)
        state = DOMContentLoaded() | Selector(".x")
        assert await state.check(page, None) is True

    @pytest.mark.asyncio
    async def test_both_false(self):
        page = make_page(evaluate_result="loading", locator_count=0)
        state = DOMContentLoaded() | Selector(".x")
        assert await state.check(page, None) is False


# ---------------------------------------------------------------------------
# Not
# ---------------------------------------------------------------------------


class TestNot:
    @pytest.mark.asyncio
    async def test_negates_true(self):
        page = make_page(evaluate_result="complete")
        state = Not(DOMContentLoaded())
        assert await state.check(page, None) is False

    @pytest.mark.asyncio
    async def test_negates_false(self):
        page = make_page(evaluate_result="loading")
        state = Not(DOMContentLoaded())
        assert await state.check(page, None) is True

    @pytest.mark.asyncio
    async def test_via_invert_operator(self):
        page = make_page(evaluate_result="complete")
        state = ~DOMContentLoaded()
        assert await state.check(page, None) is False


# ---------------------------------------------------------------------------
# Primitive states
# ---------------------------------------------------------------------------


class TestDOMContentLoaded:
    @pytest.mark.asyncio
    async def test_complete(self):
        page = make_page(evaluate_result="complete")
        assert await DOMContentLoaded().check(page, None) is True

    @pytest.mark.asyncio
    async def test_interactive(self):
        page = make_page(evaluate_result="interactive")
        assert await DOMContentLoaded().check(page, None) is True

    @pytest.mark.asyncio
    async def test_loading(self):
        page = make_page(evaluate_result="loading")
        assert await DOMContentLoaded().check(page, None) is False


class TestSelector:
    @pytest.mark.asyncio
    async def test_found(self):
        page = make_page(locator_count=3)
        assert await Selector(".items").check(page, None) is True
        page.locator.assert_called_with(".items")

    @pytest.mark.asyncio
    async def test_not_found(self):
        page = make_page(locator_count=0)
        assert await Selector(".missing").check(page, None) is False


class TestSubstringMatch:
    @pytest.mark.asyncio
    async def test_present_in_text(self):
        page = make_page(inner_text="product list loaded")
        assert await SubstringMatch("product").check(page, None) is True

    @pytest.mark.asyncio
    async def test_absent_in_text(self):
        page = make_page(inner_text="empty page")
        assert await SubstringMatch("product").check(page, None) is False

    @pytest.mark.asyncio
    async def test_html_mode_searches_source(self):
        page = make_page(html='<div class="product-card">item</div>', inner_text="item")
        # html=True searches raw source including tag attributes
        assert await SubstringMatch("product-card", html=True).check(page, None) is True

    @pytest.mark.asyncio
    async def test_html_mode_false_checks_text(self):
        page = make_page(html='<div class="product-card">item</div>', inner_text="item")
        # default (html=False) searches inner_text, not class attributes
        assert await SubstringMatch("product-card").check(page, None) is False

    @pytest.mark.asyncio
    async def test_inner_text_error_falls_back_to_html(self):
        page = make_page(html="<html>hello</html>")
        page.inner_text = AsyncMock(side_effect=Exception("no body"))
        assert await SubstringMatch("hello").check(page, None) is True


class TestTimeDelay:
    @pytest.mark.asyncio
    async def test_not_elapsed(self):
        state = TimeDelay(5000)
        page = make_page()
        assert await state.check(page, None) is False

    @pytest.mark.asyncio
    async def test_elapsed(self):
        state = TimeDelay(10)
        page = make_page()
        await state.check(page, None)  # starts timer
        await asyncio.sleep(0.02)
        assert await state.check(page, None) is True


class TestHTTPStatus:
    @pytest.mark.asyncio
    async def test_match(self):
        page = make_page()
        resp = make_response(status=200)
        assert await HTTPStatus(200).check(page, resp) is True

    @pytest.mark.asyncio
    async def test_mismatch(self):
        page = make_page()
        resp = make_response(status=429)
        assert await HTTPStatus(200).check(page, resp) is False

    @pytest.mark.asyncio
    async def test_no_response(self):
        page = make_page()
        assert await HTTPStatus(200).check(page, None) is False

    @pytest.mark.asyncio
    async def test_callable_true(self):
        page = make_page()
        resp = make_response(status=201)
        assert await HTTPStatus(lambda s: 200 <= s < 300).check(page, resp) is True

    @pytest.mark.asyncio
    async def test_callable_false(self):
        page = make_page()
        resp = make_response(status=404)
        assert await HTTPStatus(lambda s: 200 <= s < 300).check(page, resp) is False

    @pytest.mark.asyncio
    async def test_callable_no_response(self):
        page = make_page()
        assert await HTTPStatus(lambda s: s == 200).check(page, None) is False


class TestResponseHeader:
    @pytest.mark.asyncio
    async def test_match(self):
        page = make_page()
        resp = make_response(headers={"content-type": "text/html"})
        assert await ResponseHeader("Content-Type", "text/html").check(page, resp) is True

    @pytest.mark.asyncio
    async def test_mismatch(self):
        page = make_page()
        resp = make_response(headers={"content-type": "application/json"})
        assert await ResponseHeader("Content-Type", "text/html").check(page, resp) is False

    @pytest.mark.asyncio
    async def test_missing_header(self):
        page = make_page()
        resp = make_response(headers={})
        assert await ResponseHeader("X-Custom", "val").check(page, resp) is False

    @pytest.mark.asyncio
    async def test_callable_match(self):
        page = make_page()
        resp = make_response(headers={"x-cache": "HIT from cdn"})
        assert await ResponseHeader("x-cache", lambda v: v.startswith("HIT")).check(page, resp) is True

    @pytest.mark.asyncio
    async def test_callable_mismatch(self):
        page = make_page()
        resp = make_response(headers={"x-cache": "MISS"})
        assert await ResponseHeader("x-cache", lambda v: v.startswith("HIT")).check(page, resp) is False


class TestURLMatches:
    @pytest.mark.asyncio
    async def test_match(self):
        page = make_page(url="https://example.com/products?page=2")
        assert await URLMatches(r"/products").check(page, None) is True

    @pytest.mark.asyncio
    async def test_regex_pattern(self):
        page = make_page(url="https://example.com/products/12345")
        assert await URLMatches(r"/products/\d+$").check(page, None) is True

    @pytest.mark.asyncio
    async def test_no_match(self):
        page = make_page(url="https://example.com/login")
        assert await URLMatches(r"/products").check(page, None) is False
