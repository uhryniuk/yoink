"""Async Playwright driver — core browser automation primitives used by workers."""

from __future__ import annotations

import asyncio

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from yoink.common import clean_html as _clean_html
from yoink.models import Action, ExtractReq

# Default UA — looks like a real desktop Chrome
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Browser launch args — disable unnecessary features, ensure container compatibility
BROWSER_ARGS = [
    "--disable-web-security",
    "--disable-site-isolation-trials",
    "--disable-notifications",
    "--no-sandbox",           # required in containers (no user namespace)
    "--disable-dev-shm-usage",  # /dev/shm is often small in containers
]

# Adapted from the original JS_WAIT_DOM_IDLE — rewired for Playwright's
# evaluate() API which passes args as a single array and handles Promise resolution.
_JS_WAIT_DOM_STABLE = """
(args) => {
    const [timeoutMs, stabilityMs] = args;
    return new Promise(resolve => {
        let stableTimer = null;

        const settle = () => {
            observer.disconnect();
            if (stableTimer) clearTimeout(stableTimer);
            resolve(true);
        };

        const resetStableTimer = () => {
            if (stableTimer) clearTimeout(stableTimer);
            stableTimer = setTimeout(settle, stabilityMs);
        };

        const observer = new MutationObserver(resetStableTimer);
        observer.observe(document.body, {
            childList: true,
            attributes: true,
            subtree: true,
        });

        // Start the stability countdown immediately (handles already-stable pages)
        resetStableTimer();

        // Hard ceiling — resolve regardless after timeoutMs
        setTimeout(() => {
            observer.disconnect();
            if (stableTimer) clearTimeout(stableTimer);
            resolve(false);
        }, timeoutMs);
    });
}
"""


async def launch_browser(p: Playwright, headless: bool = True, user_agent: str | None = None) -> Browser:
    """Launch a Chromium browser with sensible defaults for scraping."""
    return await p.chromium.launch(headless=headless, args=BROWSER_ARGS)


async def open_context(
    browser: Browser,
    req: ExtractReq,
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


async def navigate(page: Page, req: ExtractReq) -> str:
    """Navigate to req.url, execute actions, wait for stability.

    Returns the final URL (after any redirects).
    """
    await page.goto(
        req.url,
        timeout=req.timeout * 1000,
        wait_until="domcontentloaded",
    )

    for action in req.actions:
        await execute_action(page, action)

    await wait_for_stable(page, req.wait_for, req.timeout)

    return page.url


async def execute_action(page: Page, action: Action) -> None:
    """Execute a single browser action against the page."""
    _CLICK_TIMEOUT = 10_000

    if action.type == "click":
        await page.locator(f"xpath={action.selector}").first.click(timeout=_CLICK_TIMEOUT)

    elif action.type == "setValue":
        loc = page.locator(f"xpath={action.selector}").first
        await loc.clear()
        await loc.fill(action.value or "")

    elif action.type == "setValueAndEnter":
        loc = page.locator(f"xpath={action.selector}").first
        await loc.clear()
        await loc.fill(action.value or "")
        await loc.press("Enter")

    elif action.type == "hover":
        await page.locator(f"xpath={action.selector}").first.hover()

    elif action.type == "scroll":
        await page.evaluate("window.scrollBy(0, window.innerHeight)")

    elif action.type == "wait":
        await asyncio.sleep((action.duration_ms or 1000) / 1000)

    else:
        raise ValueError(f"Unknown action type: {action.type!r}")


async def wait_for_stable(page: Page, wait_for: str, timeout: float) -> None:
    """Wait for the page to reach a stable state.

    ``wait_for`` can be:
    - ``"networkidle"`` — no network requests for 500ms
    - ``"domcontentloaded"`` — initial HTML parsed
    - any CSS selector string — wait for that element to appear

    Always follows up with a DOM mutation stability check (100ms of no mutations).
    Timeouts are treated as best-effort — a slow page is still returned.
    """
    timeout_ms = int(timeout * 1000)

    try:
        if wait_for == "networkidle":
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        elif wait_for == "domcontentloaded":
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        else:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
    except Exception:
        pass  # timeout is acceptable — return best-effort HTML

    # Wait for DOM mutations to settle (100ms quiet window)
    try:
        await page.evaluate(_JS_WAIT_DOM_STABLE, [timeout_ms, 100])
    except Exception:
        pass


async def extract_html(page: Page, clean: bool = False) -> str:
    """Return the full page HTML, optionally cleaned of scripts/styles/noise."""
    html = await page.content()
    return _clean_html(html) if clean else html


async def take_screenshot(page: Page) -> bytes:
    """Return a full-page PNG screenshot as bytes."""
    return await page.screenshot(full_page=True, animations="disabled")
