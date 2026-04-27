"""Reconciler — drives a State against a live Playwright page on a tick loop.

The reconciler is the bridge between the State system and the browser.
It polls ``state.check()`` at ``tick_ms`` intervals until the state
resolves or the timeout expires. Retries re-navigate and start fresh.
"""

from __future__ import annotations

import asyncio
import time

from playwright.async_api import Page, Response

from yoink.states import TICK_MS, State


def _reset_state(state: State) -> None:
    """Reset any internal evaluation state for a fresh retry cycle."""
    if hasattr(state, "reset"):
        state.reset()
    if hasattr(state, "_settled"):
        state._settled = False
    if hasattr(state, "_installed"):
        state._installed = False
    if hasattr(state, "_start"):
        state._start = None
    if hasattr(state, "_left_resolved"):
        state._left_resolved = False


async def reconcile(
    page: Page,
    response: Response | None,
    state: State,
    timeout: float = 30.0,
    tick_ms: int = TICK_MS,
) -> str:
    """Evaluate ``state`` against ``page`` on a tick loop.

    Args:
        page: Live Playwright page (already navigated).
        response: The HTTP response from navigation, or None.
        state: The State expression to evaluate.
        timeout: Maximum seconds to wait for the state to resolve.
        tick_ms: Milliseconds between each ``state.check()`` call.

    Returns:
        ``"success"`` if the state resolved, ``"timeout"`` if it didn't.
    """
    tick_secs = tick_ms / 1000
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            if await state.check(page, response):
                return "success"
        except Exception:
            # State check failed (page closed, JS error, etc.)
            # Keep ticking — transient failures shouldn't abort early.
            pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await asyncio.sleep(min(tick_secs, remaining))

    return "timeout"
