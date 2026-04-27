"""Unit tests for rate_limiter.py."""

import multiprocessing
import time

import pytest

from yoink.config import RateLimitConfig
from yoink.rate_limiter import RateLimiter


@pytest.fixture()
def manager():
    m = multiprocessing.Manager()
    yield m
    m.shutdown()


@pytest.fixture()
def shared_times(manager):
    return manager.dict()


async def test_no_delay_is_instant(shared_times):
    cfg = RateLimitConfig(default_delay_ms=0)
    rl = RateLimiter(shared_times, cfg)
    t = time.monotonic()
    await rl.acquire("http://example.com/a")
    await rl.acquire("http://example.com/b")
    assert time.monotonic() - t < 0.1


async def test_per_domain_delay_enforced(shared_times):
    cfg = RateLimitConfig(default_delay_ms=0, per_domain={"slow.com": 300})
    rl = RateLimiter(shared_times, cfg)

    await rl.acquire("http://slow.com/1")
    t = time.monotonic()
    await rl.acquire("http://slow.com/2")
    elapsed = time.monotonic() - t

    assert 0.25 <= elapsed <= 0.6, f"expected ~300ms, got {elapsed * 1000:.0f}ms"


async def test_different_domains_dont_block_each_other(shared_times):
    cfg = RateLimitConfig(default_delay_ms=0, per_domain={"slow.com": 500})
    rl = RateLimiter(shared_times, cfg)

    await rl.acquire("http://slow.com/1")
    t = time.monotonic()
    await rl.acquire("http://fast.com/1")  # different domain — no delay
    assert time.monotonic() - t < 0.1


async def test_default_delay_applies_to_unknown_domains(shared_times):
    cfg = RateLimitConfig(default_delay_ms=200)
    rl = RateLimiter(shared_times, cfg)

    await rl.acquire("http://any.com/1")
    t = time.monotonic()
    await rl.acquire("http://any.com/2")
    elapsed = time.monotonic() - t

    assert elapsed >= 0.15, f"expected ~200ms, got {elapsed * 1000:.0f}ms"


async def test_per_domain_overrides_default(shared_times):
    cfg = RateLimitConfig(default_delay_ms=1000, per_domain={"fast.com": 0})
    rl = RateLimiter(shared_times, cfg)

    await rl.acquire("http://fast.com/1")
    t = time.monotonic()
    await rl.acquire("http://fast.com/2")  # per_domain=0 — instant
    assert time.monotonic() - t < 0.1
