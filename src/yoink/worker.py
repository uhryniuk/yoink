"""Worker process: one asyncio event loop + one Playwright browser per process."""

from __future__ import annotations

import asyncio
import time
from multiprocessing import Queue

from playwright.async_api import async_playwright

from yoink.config import WorkerConfig
from yoink.drivers import playwright as pw
from yoink.models import Request, Result
from yoink.rate_limiter import RateLimiter
from yoink.reconciler import reconcile, _reset_state
from yoink.states import DOMContentLoaded, State

# Sentinel pushed into the input queue to signal a worker to exit cleanly.
SENTINEL = None


def worker_main(
    input_q: Queue,
    output_q: Queue,
    config: WorkerConfig,
    rate_limiter: RateLimiter,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> None:
    """Entry point for each worker process. Called after spawn/forkserver."""
    asyncio.run(_run(input_q, output_q, config, rate_limiter, guard, middleware_state))


async def _run(
    input_q: Queue,
    output_q: Queue,
    config: WorkerConfig,
    rate_limiter: RateLimiter,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> None:
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(config.page_limit)
    pending: set[asyncio.Task] = set()

    async with async_playwright() as p:
        browser = await pw.launch_browser(p, headless=config.headless)
        browser_open = True
        idle_deadline = loop.time() + config.idle_timeout_secs

        while True:
            req = await _dequeue(loop, input_q, timeout=1.0)

            if req is SENTINEL:
                break

            if req is None:
                # Queue timeout — check idle browser shutdown
                if not pending and browser_open and loop.time() > idle_deadline:
                    await browser.close()
                    browser_open = False
                continue

            # Reopen browser if it was closed due to idle
            if not browser_open:
                browser = await pw.launch_browser(p, headless=config.headless)
                browser_open = True

            idle_deadline = loop.time() + config.idle_timeout_secs
            await semaphore.acquire()

            task = asyncio.create_task(
                _fetch(browser, req, output_q, rate_limiter, semaphore, config, guard, middleware_state)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

        # Drain any in-flight tasks before exiting
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if browser_open:
            await browser.close()


async def _dequeue(loop: asyncio.AbstractEventLoop, q: Queue, timeout: float):
    """Pull one item from a multiprocessing.Queue without blocking the event loop."""
    try:
        return await loop.run_in_executor(None, q.get, True, timeout)
    except Exception:
        return None  # queue.Empty on timeout


async def _fetch(
    browser,
    req: Request,
    output_q: Queue,
    rate_limiter: RateLimiter,
    semaphore: asyncio.Semaphore,
    config: WorkerConfig,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> None:
    """Fetch one URL, retrying up to req.retries times on error or timeout."""
    start = time.monotonic()
    attempts = 1 + max(0, req.retries)
    result: Result | None = None

    for attempt in range(attempts):
        try:
            result = await _fetch_once(browser, req, rate_limiter, config, guard, middleware_state)
            # Only retry on error or timeout, not guard_failed or success
            if result.terminal not in ("error", "timeout") or attempt == attempts - 1:
                break
        except Exception as exc:
            if attempt == attempts - 1:
                result = Result(request=req, url=req.url, html="", terminal="error", error=exc)
            # else: loop continues to retry

    result.duration_ms = int((time.monotonic() - start) * 1000)
    output_q.put(result)
    semaphore.release()


async def _fetch_once(
    browser,
    req: Request,
    rate_limiter: RateLimiter,
    config: WorkerConfig,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> Result:
    """Single fetch attempt — pre_actions, navigate, actions, reconcile, extract HTML."""
    ctx = await pw.open_context(browser, req, user_agent=config.user_agent)
    page = await ctx.new_page()

    try:
        await rate_limiter.acquire(req.url)

        # pre_actions run before goto (intercepts, cookie injection, viewport setup)
        if req.pre_actions:
            await pw.execute_actions(page, req.pre_actions)

        final_url, response = await pw.navigate(page, req)

        # Capture HTTP metadata from response
        status = response.status if response else None
        resp_headers = await response.all_headers() if response else {}

        # Guard — fail fast if violated
        if guard is not None:
            guard_ok = await guard.check(page, response)
            if not guard_ok:
                html = await pw.extract_html(page, clean=req.clean_html)
                return Result(
                    request=req, url=final_url, html=html,
                    status=status, headers=resp_headers,
                    terminal="guard_failed",
                )

        # post-navigate actions run before the reconciler tick loop
        if req.actions:
            await pw.execute_actions(page, req.actions)

        # Build effective state: middleware AND request state
        state = _effective_state(req, middleware_state)

        # Reconcile
        terminal = await reconcile(page, response, state, timeout=req.timeout, tick_ms=req.tick_ms)

        html = await pw.extract_html(page, clean=req.clean_html)
        screenshot = await pw.take_screenshot(page) if req.screenshot else None

        return Result(
            request=req, url=final_url, html=html,
            status=status, headers=resp_headers,
            screenshot=screenshot, terminal=terminal,
        )
    finally:
        await ctx.close()


def _effective_state(req: Request, middleware_state: State | None) -> State:
    """Compose the per-request state with engine-level middleware state."""
    req_state = req.state or DOMContentLoaded()

    if middleware_state is not None:
        return middleware_state & req_state
    return req_state
