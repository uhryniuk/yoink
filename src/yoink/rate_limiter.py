"""Process-safe per-domain rate limiting."""

from __future__ import annotations

import asyncio
import time
from multiprocessing.managers import DictProxy
from urllib.parse import urlparse

from yoink.config import RateLimitConfig


class RateLimiter:
    """Enforces a minimum delay between requests to the same domain.

    Uses a shared ``multiprocessing.Manager().dict()`` so the delay is
    coordinated across all worker processes — not just within one process.
    """

    def __init__(self, shared_times: DictProxy, config: RateLimitConfig) -> None:
        self._times = shared_times
        self._config = config

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _delay_ms(self, domain: str) -> int:
        return self._config.per_domain.get(domain, self._config.default_delay_ms)

    async def acquire(self, url: str) -> None:
        """Async-sleep until the domain's delay has elapsed since its last request."""
        domain = self._domain(url)
        delay_ms = self._delay_ms(domain)
        if delay_ms <= 0:
            return

        now = time.monotonic()
        last = self._times.get(domain, 0.0)
        wait_secs = (last + delay_ms / 1000) - now

        if wait_secs > 0:
            await asyncio.sleep(wait_secs)

        self._times[domain] = time.monotonic()
