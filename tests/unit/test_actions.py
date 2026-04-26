"""Unit tests for actions.py — all Page interactions are mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_page(**evaluate_side_effects) -> MagicMock:
    """Return a mock Page with async methods pre-wired."""
    page = MagicMock()
    page.click = AsyncMock()
    page.hover = AsyncMock()
    page.fill = AsyncMock()
    page.press = AsyncMock()
    page.select_option = AsyncMock()
    page.evaluate = AsyncMock()
    return page


# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------

class TestActionABC:
    def test_cannot_instantiate_bare(self):
        with pytest.raises(TypeError):
            Action()

    def test_custom_subclass_works(self):
        class MyAction(Action):
            async def run(self, page):
                pass

        a = MyAction()
        assert isinstance(a, Action)


# ---------------------------------------------------------------------------
# Scroll
# ---------------------------------------------------------------------------

class TestScroll:
    @pytest.mark.asyncio
    async def test_scroll_down(self):
        page = make_page()
        await Scroll(direction="down", px=200).run(page)
        page.evaluate.assert_awaited_once_with("window.scrollBy(0, 200)")

    @pytest.mark.asyncio
    async def test_scroll_up(self):
        page = make_page()
        await Scroll(direction="up", px=100).run(page)
        page.evaluate.assert_awaited_once_with("window.scrollBy(0, -100)")

    @pytest.mark.asyncio
    async def test_scroll_right(self):
        page = make_page()
        await Scroll(direction="right", px=50).run(page)
        page.evaluate.assert_awaited_once_with("window.scrollBy(50, 0)")

    @pytest.mark.asyncio
    async def test_scroll_left(self):
        page = make_page()
        await Scroll(direction="left", px=75).run(page)
        page.evaluate.assert_awaited_once_with("window.scrollBy(-75, 0)")

    def test_defaults(self):
        s = Scroll()
        assert s.direction == "down"
        assert s.px == 300


# ---------------------------------------------------------------------------
# ScrollToBottom
# ---------------------------------------------------------------------------

class TestScrollToBottom:
    @pytest.mark.asyncio
    async def test_stops_when_no_movement(self):
        page = make_page()
        # Simulate page already at bottom: evaluate always returns same value
        page.evaluate = AsyncMock(return_value=500)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await ScrollToBottom(step_px=300, delay_ms=0).run(page)

        # Two stall increments needed → two scrollBy calls then stop
        calls = [str(c) for c in page.evaluate.call_args_list]
        scroll_calls = [c for c in calls if "scrollBy" in c]
        assert len(scroll_calls) == 2

    @pytest.mark.asyncio
    async def test_scrolls_until_stall(self):
        page = make_page()
        # Two iterations of movement, then two stalls to exit (stall counter needs 2)
        # Calls per iteration: before(scrollY), scrollBy, after(scrollY) → 3 per round
        # Round 1: 0→300 (move), Round 2: 300→600 (move), Round 3+4: 600→600 (stall x2)
        positions = [0, 300, 300, 600, 600, 600, 600, 600]
        position_iter = iter(positions)

        async def evaluate_side_effect(expr):
            if "scrollY" in expr:
                return next(position_iter)
            return None

        page.evaluate = AsyncMock(side_effect=evaluate_side_effect)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await ScrollToBottom(step_px=300, delay_ms=0).run(page)

        scroll_calls = [
            c for c in page.evaluate.call_args_list
            if "scrollBy" in str(c)
        ]
        assert len(scroll_calls) >= 1

    def test_defaults(self):
        s = ScrollToBottom()
        assert s.step_px == 300
        assert s.delay_ms == 100


# ---------------------------------------------------------------------------
# Click
# ---------------------------------------------------------------------------

class TestClick:
    @pytest.mark.asyncio
    async def test_clicks_selector(self):
        page = make_page()
        await Click(selector=".btn-submit").run(page)
        page.click.assert_awaited_once_with(".btn-submit")

    def test_requires_selector(self):
        with pytest.raises(TypeError):
            Click()


# ---------------------------------------------------------------------------
# Hover
# ---------------------------------------------------------------------------

class TestHover:
    @pytest.mark.asyncio
    async def test_hovers_selector(self):
        page = make_page()
        await Hover(selector="#menu-item").run(page)
        page.hover.assert_awaited_once_with("#menu-item")


# ---------------------------------------------------------------------------
# Fill
# ---------------------------------------------------------------------------

class TestFill:
    @pytest.mark.asyncio
    async def test_fills_input(self):
        page = make_page()
        await Fill(selector="#search", value="yoink").run(page)
        page.fill.assert_awaited_once_with("#search", "yoink")

    @pytest.mark.asyncio
    async def test_fill_empty_string(self):
        page = make_page()
        await Fill(selector="#q", value="").run(page)
        page.fill.assert_awaited_once_with("#q", "")


# ---------------------------------------------------------------------------
# Wait
# ---------------------------------------------------------------------------

class TestWait:
    @pytest.mark.asyncio
    async def test_waits_correct_duration(self):
        page = make_page()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await Wait(ms=500).run(page)
        mock_sleep.assert_awaited_once_with(0.5)

    @pytest.mark.asyncio
    async def test_zero_wait(self):
        page = make_page()
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await Wait(ms=0).run(page)
        mock_sleep.assert_awaited_once_with(0.0)


# ---------------------------------------------------------------------------
# PressKey
# ---------------------------------------------------------------------------

class TestPressKey:
    @pytest.mark.asyncio
    async def test_presses_key(self):
        page = make_page()
        await PressKey(selector="#q", key="Enter").run(page)
        page.press.assert_awaited_once_with("#q", "Enter")

    @pytest.mark.asyncio
    async def test_presses_tab(self):
        page = make_page()
        await PressKey(selector="input[name=user]", key="Tab").run(page)
        page.press.assert_awaited_once_with("input[name=user]", "Tab")


# ---------------------------------------------------------------------------
# SelectOption
# ---------------------------------------------------------------------------

class TestSelectOption:
    @pytest.mark.asyncio
    async def test_selects_option(self):
        page = make_page()
        await SelectOption(selector="#sort", value="price-asc").run(page)
        page.select_option.assert_awaited_once_with("#sort", value="price-asc")


# ---------------------------------------------------------------------------
# EvaluateJS
# ---------------------------------------------------------------------------

class TestEvaluateJS:
    @pytest.mark.asyncio
    async def test_evaluates_expression(self):
        page = make_page()
        await EvaluateJS(expression="window.scrollTo(0, document.body.scrollHeight)").run(page)
        page.evaluate.assert_awaited_once_with(
            "window.scrollTo(0, document.body.scrollHeight)"
        )

    @pytest.mark.asyncio
    async def test_evaluate_empty_string(self):
        page = make_page()
        await EvaluateJS(expression="").run(page)
        page.evaluate.assert_awaited_once_with("")


# ---------------------------------------------------------------------------
# Integration: actions on Request
# ---------------------------------------------------------------------------

class TestActionsOnRequest:
    def test_request_default_empty_actions(self):
        from yoink.models import Request
        req = Request(url="https://example.com")
        assert req.actions == []
        assert req.pre_actions == []

    def test_request_accepts_actions(self):
        from yoink.models import Request
        req = Request(
            url="https://example.com",
            actions=[ScrollToBottom(), Wait(ms=200)],
            pre_actions=[EvaluateJS("document.cookie = 'test=1'")],
        )
        assert len(req.actions) == 2
        assert len(req.pre_actions) == 1

    def test_actions_excluded_from_to_dict(self):
        from yoink.models import Request
        req = Request(
            url="https://example.com",
            actions=[Click(".btn")],
            pre_actions=[Wait(100)],
        )
        d = req.to_dict()
        assert "actions" not in d
        assert "pre_actions" not in d

    def test_state_excluded_from_to_dict(self):
        from yoink.models import Request
        from yoink.states import Selector
        req = Request(url="https://example.com", state=Selector(".content"))
        d = req.to_dict()
        assert "state" not in d

    def test_json_roundtrip_with_actions(self):
        from yoink.models import Request
        req = Request(
            url="https://example.com",
            actions=[Click(".btn"), Wait(100)],
            tick_ms=500,
            retries=2,
        )
        restored = Request.from_json(req.to_json())
        assert restored.url == req.url
        assert restored.tick_ms == 500
        assert restored.retries == 2
        # actions not serialized — restored from default
        assert restored.actions == []

    def test_tick_ms_and_retries_in_dict(self):
        from yoink.models import Request
        req = Request(url="https://example.com", tick_ms=100, retries=3)
        d = req.to_dict()
        assert d["tick_ms"] == 100
        assert d["retries"] == 3


# ---------------------------------------------------------------------------
# Integration: execute_actions driver helper
# ---------------------------------------------------------------------------

class TestWaitForSelector:
    @pytest.mark.asyncio
    async def test_waits_for_selector(self):
        page = make_page()
        page.wait_for_selector = AsyncMock()
        await WaitForSelector(selector=".modal", timeout_ms=3000).run(page)
        page.wait_for_selector.assert_awaited_once_with(".modal", timeout=3000)

    def test_default_timeout(self):
        w = WaitForSelector(selector=".x")
        assert w.timeout_ms == 5000


class TestRouteBlock:
    @pytest.mark.asyncio
    async def test_blocks_single_pattern(self):
        page = make_page()
        page.route = AsyncMock()
        await RouteBlock("**/ads/**").run(page)
        assert page.route.call_count == 1
        call_args = page.route.call_args_list[0]
        assert call_args[0][0] == "**/ads/**"

    @pytest.mark.asyncio
    async def test_blocks_multiple_patterns(self):
        page = make_page()
        page.route = AsyncMock()
        await RouteBlock("**/ads/**", "**/analytics/**", "**gtm**").run(page)
        assert page.route.call_count == 3
        patterns = [c[0][0] for c in page.route.call_args_list]
        assert "**/ads/**" in patterns
        assert "**/analytics/**" in patterns
        assert "**gtm**" in patterns

    @pytest.mark.asyncio
    async def test_route_handler_aborts(self):
        page = make_page()
        captured_handler = None

        async def capture_route(pattern, handler):
            nonlocal captured_handler
            captured_handler = handler

        page.route = AsyncMock(side_effect=capture_route)
        await RouteBlock("**/ads/**").run(page)

        # The handler should call route.abort()
        mock_route = AsyncMock()
        await captured_handler(mock_route)
        mock_route.abort.assert_awaited_once()

    def test_no_patterns_noop(self):
        rb = RouteBlock()
        assert rb.patterns == ()


class TestExecuteActions:
    @pytest.mark.asyncio
    async def test_runs_actions_in_order(self):
        from yoink.drivers.playwright import execute_actions

        order = []

        class TrackAction(Action):
            def __init__(self, name: str):
                self.name = name

            async def run(self, page):
                order.append(self.name)

        page = make_page()
        await execute_actions(page, [TrackAction("a"), TrackAction("b"), TrackAction("c")])
        assert order == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self):
        from yoink.drivers.playwright import execute_actions
        page = make_page()
        await execute_actions(page, [])  # should not raise
