# Yoink — Architecture

## Overview

Yoink is a Python library and CLI for scraping dynamic web pages at scale using async Playwright + multiprocessing. The architecture is designed for maximum throughput, fault tolerance, and ease of use — from a one-liner to a full web service.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Browser driver | async Playwright only | Faster, modern API, native asyncio, lightweight browser contexts |
| Input concurrency | Shared `multiprocessing.Queue` | Simple, self-balancing producer-consumer; no reconciler needed |
| Intra-worker concurrency | `asyncio` + N pages per worker | One browser per process, N concurrent contexts per browser |
| Results flow | Shared results queue | Uniform across library, CLI, and service |
| Rate limiting | Per-domain configurable delay | Targeted, courteous; no global cap needed |
| Proxy support | Per-request via `ExtractReq` | First-class, Playwright-native |
| Config format | TOML + env vars (`YK_` prefix) + XDG | Standard, composable |
| Logging | structlog → JSONL to stdout | Structured, parseable, minimal option available |

## High-Level Architecture

```
                    ┌─────────────────────────────┐
                    │         Public API           │
                    │  yoink.get() / get_all()     │
                    │  yoink.Engine / yoink.stream │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │           Engine             │
                    │  - spawns worker processes   │
                    │  - owns input queue          │
                    │  - owns results queue        │
                    │  - graceful shutdown         │
                    └──────┬──────────────┬────────┘
                           │              │
               ┌───────────▼──┐    ┌──────▼───────────┐
               │  Input Queue │    │  Results Queue   │
               │(multiprocess)│    │ (multiprocess)   │
               └───────┬──────┘    └──────────────────┘
                       │                   ▲
        ┌──────────────┼──────────────┐    │
        ▼              ▼              ▼    │
  ┌──────────┐  ┌──────────┐  ┌──────────┐│
  │ Worker 0 │  │ Worker 1 │  │ Worker N ││
  │(process) │  │(process) │  │(process) ││
  │          │  │          │  │          ││
  │ asyncio  │  │ asyncio  │  │ asyncio  ││
  │ Playwright  │ Playwright  │ Playwright ──┘
  │ N pages  │  │ N pages  │  │ N pages  │
  └──────────┘  └──────────┘  └──────────┘
```

## Project Structure

```
src/yoink/
├── __init__.py          # Public API: get, get_all, stream, Engine, ExtractReq, ExtractResult
├── models.py            # ExtractReq, ExtractResult, RetryPolicy, ProxyConfig, Action
├── config.py            # Config, WorkerConfig, RateLimitConfig, LogConfig
├── engine.py            # Engine — manages worker pool and queues
├── worker.py            # Worker process: asyncio event loop + Playwright browser
├── rate_limiter.py      # Per-domain delay (process-safe)
├── logging.py           # structlog setup, JSONL formatter
├── exceptions.py        # Exception hierarchy
├── common.py            # URL validation, HTML cleaning utilities
├── cli.py               # CLI (yoink + yk entrypoints)
└── drivers/
    └── playwright.py    # Async PlaywrightDriver
```

## Component Responsibilities

### `models.py`
Core data structures. No dependencies on other yoink modules.

- `ExtractReq` — unit of work: URL + options (wait strategy, timeout, retry, proxy, actions, screenshot)
- `ExtractResult` — output: HTML, final URL, screenshot, duration, error
- `RetryPolicy` — max attempts, backoff factor
- `ProxyConfig` — proxy server URL, optional credentials
- `Action` — browser action (click, setValue, hover, scroll, wait) with selector + value

All dataclasses. `ExtractReq` maps directly to the JSON body accepted by the service.

### `config.py`
Configuration hierarchy. Loaded once at startup.

```
Defaults → XDG (~/.config/yoink/config.toml) → --config flag → YK_ env vars
```

Nested structure: `Config` contains `WorkerConfig`, `RateLimitConfig`, `LogConfig`.

Env var format: `YK_WORKERS__COUNT=8`, `YK_LOG__LEVEL=DEBUG` (double underscore = nested key).

### `engine.py`
The central coordinator. Owns the worker process pool and both queues.

- Uses `multiprocessing` with `spawn` start method (required for Playwright compatibility)
- Context manager: `with Engine(config) as engine:`
- `submit(req)` — adds to input queue
- `results()` — iterator over output queue, blocks until all submitted work is done
- `stream(reqs)` — submit + iterate in one call
- `shutdown(wait=True)` — sends sentinels, waits for workers to drain and exit

### `worker.py`
One instance per OS process. Each worker owns one Playwright browser.

- `asyncio.Semaphore(pages_per_worker)` caps concurrent pages within the worker
- Pulls `ExtractReq` from shared input queue (blocking get via executor to not block asyncio loop)
- Pushes `ExtractResult` to shared results queue
- Idle timer: if no work for `idle_timeout_secs`, closes browser (re-opens on next request)
- Retries handled here via tenacity, using `req.retry` policy

### `rate_limiter.py`
Process-safe per-domain delay enforcement.

- Shared `multiprocessing.Manager().dict()` tracks last-request timestamp per domain
- `RateLimiter.acquire(url)` — async sleeps if needed before a request proceeds
- Domain extracted via `urllib.parse.urlparse`

### `drivers/playwright.py`
Thin async wrapper over Playwright. Used only by `worker.py`.

- `open_page(browser, req)` — creates a browser context with proxy/headers, opens page
- `navigate(page, req)` — goes to URL, executes actions, waits for stability
- `extract(page)` — returns final URL + HTML (optionally cleaned)
- `screenshot(page)` — returns PNG bytes
- DOM stability check: polls `document.readyState` and `performance.getEntriesByType`

### `cli.py`
CLI. Two entrypoints: `yoink` and `yk`.

Key commands:
- `yoink <input>` — scrape URL(s), write to stdout (default) or `--output` dir / `--tarball`
- `yoink --stream <input>` — JSONL output as results arrive

## Multiprocessing Safety

**Critical:** Playwright must be initialized **after** forking. We use `spawn` (not `fork`) as the start method to guarantee this:

```python
# In engine.py, before starting any workers:
multiprocessing.set_start_method('spawn', force=True)
```

Each worker initializes Playwright inside its own process entry point — never before.

## Logging

structlog configured to emit JSONL to stdout:

```json
{"timestamp": "2026-03-15T12:00:00Z", "level": "info", "event": "page fetched", "url": "https://...", "duration_ms": 342}
```

Minimal mode (config: `log.minimal = true`): emits only `timestamp` and `event` fields.
