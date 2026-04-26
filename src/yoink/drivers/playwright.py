"""Async Playwright driver — browser lifecycle and navigation primitives."""

from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response

from yoink.common import clean_html as _clean_html
from yoink.models import Request

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BROWSER_ARGS = [
    "--disable-web-security",
    "--disable-site-isolation-trials",
    "--disable-notifications",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


async def launch_browser(p: Playwright, headless: bool = True) -> Browser:
    """Launch a Chromium browser with sensible defaults for scraping."""
    return await p.chromium.launch(headless=headless, args=BROWSER_ARGS)


async def open_context(
    browser: Browser,
    req: Request,
    user_agent: str | None = None,
) -> BrowserContext:
    """Open an isolated browser context configured from the request."""
    proxy = None
    if req.proxy:
        proxy = {"server": req.proxy.server}
        if req.proxy.username:
            proxy["username"] = req.proxy.username
            proxy["password"] = req.proxy.password or ""

    return await browser.new_context(
        user_agent=user_agent or _DEFAULT_USER_AGENT,
        extra_http_headers=req.headers,
        proxy=proxy,
        ignore_https_errors=True,
    )


async def navigate(page: Page, req: Request) -> tuple[str, Response | None]:
    """Navigate to ``req.url`` and return ``(final_url, response)``.

    The response object carries HTTP status and headers for use by
    the reconciler's guard and HTTP-level states.
    """
    response = await page.goto(
        req.url,
        timeout=req.timeout * 1000,
        wait_until="domcontentloaded",
    )
    return page.url, response


async def extract_html(page: Page, clean: bool = False) -> str:
    """Return the full page HTML, optionally cleaned of scripts/styles/noise."""
    html = await page.content()
    return _clean_html(html) if clean else html


async def take_screenshot(page: Page) -> bytes:
    """Return a full-page PNG screenshot as bytes."""
    return await page.screenshot(full_page=True, animations="disabled")
