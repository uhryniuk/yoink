"""Worker process: one asyncio event loop + one Playwright browser per process."""

from __future__ import annotations

import asyncio
import time
from multiprocessing import Queue

from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential

from yoink.config import WorkerConfig
from yoink.drivers import playwright as pw
from yoink.exceptions import ScraperError
from yoink.models import ExtractReq, ExtractResult
from yoink.rate_limiter import RateLimiter

# Sentinel pushed into the input queue to signal a worker to exit cleanly
SENTINEL = None


def worker_main(
    input_q: Queue,
    output_q: Queue,
    config: WorkerConfig,
    rate_limiter: RateLimiter,
) -> None:
    """Entry point for each worker process. Called after spawn."""
    asyncio.run(_run(input_q, output_q, config, rate_limiter))


async def _run(
    input_q: Queue,
    output_q: Queue,
    config: WorkerConfig,
    rate_limiter: RateLimiter,
) -> None:
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(config.pages_per_worker)
    pending: set[asyncio.Task] = set()

    async with async_playwright() as p:
        browser = await pw.launch_browser(p, headless=config.headless)
        idle_deadline = loop.time() + config.idle_timeout_secs

        while True:
            # Non-blocking poll so we can check idle while tasks are running
            req = await _dequeue(loop, input_q, timeout=1.0)

            if req is SENTINEL:
                break

            if req is None:
                # Queue timeout — check idle browser shutdown
                if not pending and loop.time() > idle_deadline:
                    await browser.close()
                    browser = await pw.launch_browser(p, headless=config.headless)
                    idle_deadline = loop.time() + config.idle_timeout_secs
                continue

            idle_deadline = loop.time() + config.idle_timeout_secs
            await semaphore.acquire()

            task = asyncio.create_task(
                _fetch(browser, req, output_q, rate_limiter, semaphore, config)
            )
            pending.add(task)
            task.add_done_callback(pending.discard)

        # Drain any in-flight tasks before exiting
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        await browser.close()


async def _dequeue(loop: asyncio.AbstractEventLoop, q: Queue, timeout: float):
    """Pull one item from a multiprocessing.Queue without blocking the event loop."""
    try:
        return await loop.run_in_executor(None, q.get, True, timeout)
    except Exception:
        return None  # queue.Empty on timeout


async def _fetch(
    browser,
    req: ExtractReq,
    output_q: Queue,
    rate_limiter: RateLimiter,
    semaphore: asyncio.Semaphore,
    config: WorkerConfig,
) -> None:
    """Fetch one URL with retry, push ExtractResult to output_q."""
    start = time.monotonic()
    result = await _fetch_with_retry(browser, req, rate_limiter, config)
    result.duration_ms = int((time.monotonic() - start) * 1000)
    output_q.put(result)
    semaphore.release()


async def _fetch_with_retry(
    browser,
    req: ExtractReq,
    rate_limiter: RateLimiter,
    config: WorkerConfig,
) -> ExtractResult:
    attempts = req.retry.max_attempts if req.retry.retry_on_scraper_error else 1

    @retry(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=req.retry.backoff_factor, min=1, max=30),
        reraise=True,
    )
    async def _attempt() -> ExtractResult:
        ctx = await pw.open_context(browser, req, user_agent=config.user_agent)
        page = await ctx.new_page()
        try:
            await rate_limiter.acquire(req.url)
            final_url = await pw.navigate(page, req)
            html = await pw.extract_html(page, clean=req.clean_html)
            screenshot = await pw.take_screenshot(page) if req.screenshot else None
            return ExtractResult(
                request=req,
                url=final_url,
                html=html,
                screenshot=screenshot,
            )
        finally:
            await ctx.close()

    try:
        return await _attempt()
    except Exception as exc:
        return ExtractResult(request=req, url=req.url, html="", error=exc)
