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
from yoink.reconciler import reconcile
from yoink.states import DOMContentLoaded, State

try:
    import httpx as _httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

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
    pending: set[asyncio.Task] = set()

    async with async_playwright() as p:
        browser = await pw.launch_browser(p, headless=config.headless)

        if config.persist_context:
            # One shared context per worker — pages are pre-allocated and reused.
            # Skips ~50ms new_context() overhead per request at the cost of session isolation.
            shared_ctx = await pw.open_context(
                browser,
                Request(url=""),
                user_agent=config.user_agent,
                viewport=config.viewport,
            )
            page_pool: asyncio.Queue = asyncio.Queue()
            for _ in range(config.page_limit):
                page = await shared_ctx.new_page()
                await page_pool.put(page)

            while True:
                req = await _dequeue(loop, input_q, timeout=1.0)
                if req is SENTINEL:
                    break
                if req is None:
                    continue

                page = await page_pool.get()
                task = asyncio.create_task(
                    _fetch_pooled(page, page_pool, req, output_q, rate_limiter, config, guard, middleware_state)
                )
                pending.add(task)
                task.add_done_callback(pending.discard)

            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await shared_ctx.close()

        else:
            # Default: new BrowserContext per request — full session isolation.
            semaphore = asyncio.Semaphore(config.page_limit)
            browser_open = True
            idle_deadline = loop.time() + config.idle_timeout_secs

            while True:
                req = await _dequeue(loop, input_q, timeout=1.0)

                if req is SENTINEL:
                    break

                if req is None:
                    if not pending and browser_open and loop.time() > idle_deadline:
                        await browser.close()
                        browser_open = False
                    continue

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

    fetch_fn = _httpx_fetch if (not req.use_browser and _HTTPX_AVAILABLE) else None

    for attempt in range(attempts):
        try:
            if fetch_fn is not None:
                result = await fetch_fn(req, rate_limiter)
            else:
                result = await _fetch_once(browser, req, rate_limiter, config, guard, middleware_state)
            if result.terminal not in ("error", "timeout") or attempt == attempts - 1:
                break
        except Exception as exc:
            if attempt == attempts - 1:
                result = Result(request=req, url=req.url, html="", terminal="error", error=exc)

    result.duration_ms = int((time.monotonic() - start) * 1000)
    output_q.put(result)
    semaphore.release()


async def _fetch_pooled(
    page,
    page_pool: asyncio.Queue,
    req: Request,
    output_q: Queue,
    rate_limiter: RateLimiter,
    config: WorkerConfig,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> None:
    """Fetch using a pre-allocated page from the pool. Returns page to pool when done."""
    start = time.monotonic()
    attempts = 1 + max(0, req.retries)
    result: Result | None = None

    fetch_fn = _httpx_fetch if (not req.use_browser and _HTTPX_AVAILABLE) else None

    for attempt in range(attempts):
        try:
            if fetch_fn is not None:
                result = await fetch_fn(req, rate_limiter)
            else:
                result = await _fetch_once_on_page(page, req, rate_limiter, config, guard, middleware_state)
            if result.terminal not in ("error", "timeout") or attempt == attempts - 1:
                break
        except Exception as exc:
            if attempt == attempts - 1:
                result = Result(request=req, url=req.url, html="", terminal="error", error=exc)

    result.duration_ms = int((time.monotonic() - start) * 1000)
    output_q.put(result)

    if fetch_fn is None:
        # Only reset the page when we actually used it
        try:
            await page.goto("about:blank", wait_until="domcontentloaded")
        except Exception:
            pass
    await page_pool.put(page)


async def _fetch_once(
    browser,
    req: Request,
    rate_limiter: RateLimiter,
    config: WorkerConfig,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> Result:
    """Single fetch attempt — pre_actions, navigate, actions, reconcile, extract HTML."""
    ctx = await pw.open_context(browser, req, user_agent=config.user_agent, viewport=config.viewport)
    page = await ctx.new_page()

    try:
        return await _fetch_once_on_page(page, req, rate_limiter, config, guard, middleware_state)
    finally:
        await ctx.close()


async def _fetch_once_on_page(
    page,
    req: Request,
    rate_limiter: RateLimiter,
    config: WorkerConfig,
    guard: State | None = None,
    middleware_state: State | None = None,
) -> Result:
    """Core fetch logic against an existing page object."""
    await rate_limiter.acquire(req.url)

    # pre_actions run before goto (intercepts, cookie injection, viewport setup)
    if req.pre_actions:
        await pw.execute_actions(page, req.pre_actions)

    final_url, response = await pw.navigate(page, req)

    status = response.status if response else None
    resp_headers = await response.all_headers() if response else {}

    # Guard — fail fast if violated
    if guard is not None:
        guard_ok = await guard.check(page, response)
        if not guard_ok:
            html = await pw.extract_html(page, clean=req.clean_html)
            return Result(
                request=req,
                url=final_url,
                html=html,
                status=status,
                headers=resp_headers,
                terminal="guard_failed",
            )

    # post-navigate actions run before the reconciler tick loop
    if req.actions:
        await pw.execute_actions(page, req.actions)

    state = _effective_state(req, middleware_state)
    terminal = await reconcile(page, response, state, timeout=req.timeout, tick_ms=req.tick_ms)

    html = await pw.extract_html(page, clean=req.clean_html)
    screenshot = await pw.take_screenshot(page) if req.screenshot else None

    return Result(
        request=req,
        url=final_url,
        html=html,
        status=status,
        headers=resp_headers,
        screenshot=screenshot,
        terminal=terminal,
    )


async def _httpx_fetch(req: Request, rate_limiter: RateLimiter) -> Result:
    """Fast HTTP fetch using httpx — no browser, no JS, no actions.

    Use for static HTML / JSON endpoints where JavaScript is not needed.
    Bypasses all Playwright overhead: no browser context, no page creation.
    """
    await rate_limiter.acquire(req.url)

    proxy_url = req.proxy.server if req.proxy else None

    cookie_header = "; ".join(f"{k}={v}" for k, v in req.cookies.items()) if req.cookies else None
    headers = dict(req.headers)
    if cookie_header:
        headers.setdefault("Cookie", cookie_header)

    async with _httpx.AsyncClient(
        proxy=proxy_url,
        timeout=req.timeout,
        follow_redirects=True,
        verify=False,
    ) as client:
        response = await client.get(req.url, headers=headers)

    html = response.text
    if req.clean_html:
        from yoink.common import clean_html as _clean

        html = _clean(html)

    return Result(
        request=req,
        url=str(response.url),
        html=html,
        status=response.status_code,
        headers=dict(response.headers),
        terminal="success",
    )


def _effective_state(req: Request, middleware_state: State | None) -> State:
    """Compose the per-request state with engine-level middleware state."""
    req_state = req.state or DOMContentLoaded()

    if middleware_state is not None:
        return middleware_state & req_state
    return req_state
