"""Async Playwright driver — browser lifecycle and navigation primitives."""

from __future__ import annotations

from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Page, Playwright, Response

from yoink.common import clean_html as _clean_html
from yoink.models import Request
from yoink.stealth import STEALTH_SCRIPT

# Matches the UA injected by default when no custom UA is set.
# Windows + Chrome 124 is the largest real-browser population segment.
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Args that improve container compatibility without exposing automation signals.
# Notably absent: --disable-web-security (very detectable), --disable-extensions
# (real Chrome has extensions), --disable-site-isolation-trials (unusual).
# --disable-blink-features=AutomationControlled suppresses the CDP automation
# banner and removes several blink-level automation hints.
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-notifications",
    "--no-first-run",
    "--no-default-browser-check",
]


async def launch_browser(p: Playwright, headless: bool = True) -> Browser:
    """Launch a Chromium browser with sensible defaults for scraping."""
    return await p.chromium.launch(headless=headless, args=BROWSER_ARGS)


async def open_context(
    browser: Browser,
    req: Request,
    user_agent: str | None = None,
    viewport: dict | None = None,
) -> BrowserContext:
    """Open an isolated browser context configured from the request."""
    proxy = None
    if req.proxy:
        proxy = {"server": req.proxy.server}
        if req.proxy.username:
            proxy["username"] = req.proxy.username
            proxy["password"] = req.proxy.password or ""

    ctx = await browser.new_context(
        user_agent=user_agent or _DEFAULT_USER_AGENT,
        extra_http_headers=req.headers,
        proxy=proxy,
        ignore_https_errors=True,
        viewport=viewport,
    )

    await ctx.add_init_script(STEALTH_SCRIPT)

    if req.cookies:
        parsed = urlparse(req.url)
        domain = parsed.hostname or ""
        await ctx.add_cookies([{"name": k, "value": v, "domain": domain, "path": "/"} for k, v in req.cookies.items()])

    return ctx


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


async def execute_actions(page: Page, actions: list) -> None:
    """Run a sequence of Action objects against the page in order."""
    for action in actions:
        await action.run(page)
