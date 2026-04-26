"""Composable page-state primitives for the yoink reconciler.

States describe conditions to check against a live Playwright page.
They compose with ``&`` (sequential AND) and ``|`` (concurrent OR),
and are evaluated on a tick interval by the reconciler.

Extend by subclassing ``State`` and implementing ``check()``.
"""

from __future__ import annotations

import abc
import re

from playwright.async_api import Page, Response

# Default tick interval (ms) for the reconciler polling loop.
# Override per-request via tick_ms= or set this at import time.
TICK_MS: int = 250


class State(abc.ABC):
    """Base class for all page-state conditions.

    Subclass and implement ``check`` to create custom states::

        class HasTable(State):
            async def check(self, page, response):
                return await page.locator("table").count() > 0
    """

    @abc.abstractmethod
    async def check(self, page: Page, response: Response | None) -> bool:
        """Return True when the condition is satisfied."""

    def __and__(self, other: State) -> AllState:
        """Sequential AND — left must resolve before right is evaluated."""
        return AllState(self, other)

    def __or__(self, other: State) -> AnyState:
        """Concurrent OR — both tick, first to return True wins."""
        return AnyState(self, other)

    def __invert__(self) -> Not:
        """Negate: ``~state`` is equivalent to ``Not(state)``."""
        return Not(self)


# ---------------------------------------------------------------------------
# Compound states
# ---------------------------------------------------------------------------


class AllState(State):
    """Sequential AND — evaluates left to right.

    Left must return True before right begins evaluation.
    Both share the same total timeout budget.
    """

    def __init__(self, left: State, right: State) -> None:
        self.left = left
        self.right = right
        self._left_resolved = False

    async def check(self, page: Page, response: Response | None) -> bool:
        if not self._left_resolved:
            if await self.left.check(page, response):
                self._left_resolved = True
            else:
                return False
        return await self.right.check(page, response)

    def reset(self) -> None:
        """Reset evaluation state for a fresh retry cycle."""
        self._left_resolved = False
        if isinstance(self.left, (AllState, AnyState)):
            self.left.reset()
        if isinstance(self.right, (AllState, AnyState)):
            self.right.reset()


class AnyState(State):
    """Concurrent OR — both states tick every cycle.

    First to return True wins. The other is abandoned.
    """

    def __init__(self, left: State, right: State) -> None:
        self.left = left
        self.right = right

    async def check(self, page: Page, response: Response | None) -> bool:
        return await self.left.check(page, response) or await self.right.check(page, response)

    def reset(self) -> None:
        """Reset evaluation state for a fresh retry cycle."""
        if isinstance(self.left, (AllState, AnyState)):
            self.left.reset()
        if isinstance(self.right, (AllState, AnyState)):
            self.right.reset()


class Not(State):
    """Negation wrapper — True when the inner state is False."""

    def __init__(self, inner: State) -> None:
        self.inner = inner

    async def check(self, page: Page, response: Response | None) -> bool:
        return not await self.inner.check(page, response)


# ---------------------------------------------------------------------------
# Primitive states
# ---------------------------------------------------------------------------


class DOMContentLoaded(State):
    """True once the initial HTML has been parsed.

    This is the default state — almost always satisfied immediately
    after navigation since Playwright waits for DOMContentLoaded
    on ``page.goto()``.
    """

    async def check(self, page: Page, response: Response | None) -> bool:
        state = await page.evaluate("() => document.readyState")
        return state in ("interactive", "complete")


class NetworkIdle(State):
    """True when no network requests have fired for ``idle_ms``.

    Implemented via Playwright's ``networkidle`` load state.
    Because this is event-driven rather than polled, the first
    ``check()`` call sets up the wait and subsequent calls return
    the cached result.
    """

    def __init__(self, idle_ms: int = 500) -> None:
        self.idle_ms = idle_ms
        self._settled = False

    async def check(self, page: Page, response: Response | None) -> bool:
        if self._settled:
            return True
        try:
            await page.wait_for_load_state("networkidle", timeout=self.idle_ms)
            self._settled = True
            return True
        except Exception:
            return False


class DOMStable(State):
    """True when the DOM has not mutated for ``quiet_ms``.

    Uses a MutationObserver injected into the page. The first call
    installs the observer; subsequent calls check if the quiet
    window has been reached.
    """

    _JS_INSTALL = """() => {
        if (window.__yoink_dom_stable !== undefined) return;
        window.__yoink_dom_stable = false;
        window.__yoink_dom_timer = null;
        const quietMs = %d;
        const reset = () => {
            if (window.__yoink_dom_timer) clearTimeout(window.__yoink_dom_timer);
            window.__yoink_dom_stable = false;
            window.__yoink_dom_timer = setTimeout(() => { window.__yoink_dom_stable = true; }, quietMs);
        };
        const obs = new MutationObserver(reset);
        obs.observe(document.body || document.documentElement, {
            childList: true, attributes: true, subtree: true
        });
        reset();
    }"""

    _JS_CHECK = "() => window.__yoink_dom_stable === true"

    def __init__(self, quiet_ms: int = 100) -> None:
        self.quiet_ms = quiet_ms
        self._installed = False

    async def check(self, page: Page, response: Response | None) -> bool:
        if not self._installed:
            await page.evaluate(self._JS_INSTALL % self.quiet_ms)
            self._installed = True
            return False
        return await page.evaluate(self._JS_CHECK)


class Selector(State):
    """True when at least one element matches the CSS selector."""

    def __init__(self, css: str) -> None:
        self.css = css

    async def check(self, page: Page, response: Response | None) -> bool:
        return await page.locator(self.css).count() > 0


class SubstringMatch(State):
    """True when ``text`` appears in the page HTML source."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def check(self, page: Page, response: Response | None) -> bool:
        html = await page.content()
        return self.text in html


class TimeDelay(State):
    """True after ``ms`` milliseconds have elapsed since first check.

    Useful as the left operand in ``TimeDelay(2000) & Selector(".x")``
    to delay evaluation of downstream states.
    """

    def __init__(self, ms: int) -> None:
        self.ms = ms
        self._start: float | None = None

    async def check(self, page: Page, response: Response | None) -> bool:
        import time

        if self._start is None:
            self._start = time.monotonic()
        elapsed_ms = (time.monotonic() - self._start) * 1000
        return elapsed_ms >= self.ms


class HTTPStatus(State):
    """True when the navigation response status matches ``code``.

    ``code`` can be an exact int or a callable that receives the status
    and returns bool::

        HTTPStatus(200)                         # exact match
        HTTPStatus(lambda s: 200 <= s < 300)    # any 2xx
        HTTPStatus(lambda s: s != 404)          # not found guard
    """

    def __init__(self, code) -> None:
        self.code = code

    async def check(self, page: Page, response: Response | None) -> bool:
        if response is None:
            return False
        if callable(self.code):
            return bool(self.code(response.status))
        return response.status == self.code


class ResponseHeader(State):
    """True when the response contains a header matching ``key`` and ``value``.

    The header name comparison is case-insensitive. The value is an
    exact match.
    """

    def __init__(self, key: str, value: str) -> None:
        self.key = key.lower()
        self.value = value

    async def check(self, page: Page, response: Response | None) -> bool:
        if response is None:
            return False
        headers = await response.all_headers()
        return headers.get(self.key, "") == self.value


class URLMatches(State):
    """True when the page's current URL matches ``pattern`` (regex)."""

    def __init__(self, pattern: str) -> None:
        self._re = re.compile(pattern)

    async def check(self, page: Page, response: Response | None) -> bool:
        return self._re.search(page.url) is not None
