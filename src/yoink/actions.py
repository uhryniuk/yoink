"""Action primitives — manipulate a page before the reconciler observes it.

Actions run sequentially. Two lifecycle slots on each Request:

  pre_actions  → page.goto() → actions → reconcile → extract HTML

pre_actions run before navigation (intercepts, cookie injection).
actions run after navigation but before the reconciler tick loop (scroll, click, fill).

Extend by subclassing Action and implementing ``run``::

    class DismissBanner(Action):
        async def run(self, page):
            try:
                await page.click("#cookie-banner button", timeout=2000)
            except Exception:
                pass
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from playwright.async_api import Page


class Action(ABC):
    @abstractmethod
    async def run(self, page: Page) -> None: ...


@dataclass
class Scroll(Action):
    """Scroll the viewport by a fixed number of pixels."""

    direction: str = "down"  # "up" | "down" | "left" | "right"
    px: int = 300

    async def run(self, page: Page) -> None:
        dx, dy = 0, 0
        if self.direction == "down":
            dy = self.px
        elif self.direction == "up":
            dy = -self.px
        elif self.direction == "right":
            dx = self.px
        elif self.direction == "left":
            dx = -self.px
        await page.evaluate(f"window.scrollBy({dx}, {dy})")


@dataclass
class ScrollToBottom(Action):
    """Scroll incrementally to the page bottom at a human-paced cadence.

    Useful for triggering lazy-loaded content that fires on scroll events.
    Stops once two consecutive steps produce no movement.
    """

    step_px: int = 300
    delay_ms: int = 100

    async def run(self, page: Page) -> None:
        stall = 0
        while stall < 2:
            before = await page.evaluate("window.scrollY + window.innerHeight")
            await page.evaluate(f"window.scrollBy(0, {self.step_px})")
            await asyncio.sleep(self.delay_ms / 1000)
            after = await page.evaluate("window.scrollY + window.innerHeight")
            if after == before:
                stall += 1
            else:
                stall = 0


@dataclass
class Click(Action):
    """Click an element by CSS selector."""

    selector: str

    async def run(self, page: Page) -> None:
        await page.click(self.selector)


@dataclass
class Hover(Action):
    """Hover over an element by CSS selector."""

    selector: str

    async def run(self, page: Page) -> None:
        await page.hover(self.selector)


@dataclass
class Fill(Action):
    """Fill an input field by CSS selector."""

    selector: str
    value: str

    async def run(self, page: Page) -> None:
        await page.fill(self.selector, self.value)


@dataclass
class Wait(Action):
    """Unconditional async delay."""

    ms: int

    async def run(self, page: Page) -> None:
        await asyncio.sleep(self.ms / 1000)


@dataclass
class PressKey(Action):
    """Press a key on a focused element."""

    selector: str
    key: str

    async def run(self, page: Page) -> None:
        await page.press(self.selector, self.key)


@dataclass
class SelectOption(Action):
    """Select a <select> option by value."""

    selector: str
    value: str

    async def run(self, page: Page) -> None:
        await page.select_option(self.selector, value=self.value)


@dataclass
class EvaluateJS(Action):
    """Evaluate arbitrary JavaScript on the page.

    Use as an escape hatch when no built-in action fits.
    The expression is passed to ``page.evaluate`` as-is.
    """

    expression: str

    async def run(self, page: Page) -> None:
        await page.evaluate(self.expression)
