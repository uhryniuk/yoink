# Yoink — Next Session Context

This document captures everything needed to continue in a fresh session.

---

## Where We Are

All 6 original feature sets complete plus 11 additional improvement iterations:

| What | Status |
|---|---|
| FS-1..6: Core redesign (Request, Result, States, Reconciler, Worker, Engine, CLI) | ✓ |
| Actions system: `pre_actions` / `actions` lifecycle, 11 built-in types | ✓ |
| Examples: quickstart, custom_state, engine_pipeline, scroll_and_scrape | ✓ |
| `Request.retries` actually wired into worker retry loop | ✓ |
| `persist_context` mode: one BrowserContext per worker for session scraping | ✓ |
| `Request.cookies` field: injects cookies before navigation | ✓ |
| `HTTPStatus` callable support: `HTTPStatus(lambda s: 200 <= s < 300)` | ✓ |
| `SubstringMatch` searches visible text by default (not raw HTML) | ✓ |
| `ResponseHeader` callable support | ✓ |
| `MinCount(selector, n)` state | ✓ |
| `All(*states)` / `Any(*states)` convenience constructors | ✓ |
| `WorkerConfig.viewport` for mobile emulation | ✓ |
| Fixed `retries`/`tick_ms` silently ignored in `get`/`get_all`/`stream` | ✓ |
| `WaitForSelector` action (event-driven, faster than polling) | ✓ |
| `RouteBlock(*patterns)` action (block ads/trackers before navigation) | ✓ |
| Bench Docker stack: static (8001), React SPA (8002), slow server (8003) | ✓ (not committed) |
| 17 bench integration tests (auto-skip when stack not running) | ✓ |
| `scripts/load_test.py` with workers × page_limit matrix sweep | ✓ (not committed) |

**171 unit tests, all passing. Version: 0.2.0.**

---

## Bench Stack

```bash
cd bench && docker compose up -d
# Services:
# http://localhost:8001  — static nginx (1000 HTML product pages)
# http://localhost:8002  — React SPA (200 products, 3-batch lazy load)
# http://localhost:8003  — slow HTTP server (?delay=N query param)
```

## Performance Ceiling (MacBook)

Single-machine ceiling: **~11 req/s** for localhost scraping.

Optimal config: `workers=1, page_limit=2`. Adding more workers or pages
on a single machine does not help (context switching + IPC overhead).

```
scale  workers  pages  ok    fail  req/s  p50ms  p95ms  p99ms
50     1        1      50    0     9.3    341    578    580
50     1        2      50    0     11.2   331    367    395
50     2        1      50    0     11.3   606    714    755
50     4        1      50    0     10.9   1146   1371   1497
```

To scale beyond ~11 req/s: run multiple yoink processes on separate
machines pointing at the same work queue.

---

## Possible Next Iterations

### Performance
- `httpx` fallback for non-JS pages — could push to 100+ req/s for static HTML
- Worker auto-scaling: ramp workers up/down based on queue depth
- Configurable `wait_until` in `navigate()` (currently hardcoded to "domcontentloaded")

### API
- `Request.intercept` field — route/intercept network requests declaratively
- `Request.emulate_device` — Playwright device descriptor (e.g., "iPhone 14")
- `Engine.on_result(callback)` — event hook for streaming results without iteration
- `yoink.crawl(url, depth=N)` — recursive scraping with link extraction

### Testing
- Parametrize bench integration tests to sweep tick_ms / page configs
- Add bench test for `RouteBlock` (measure actual speedup from blocking trackers)
- Load test against remote target (greatape.dev) to measure network-bound ceiling

---

## Key Files Reference

```
src/yoink/
  __init__.py          public API (v0.2.0)
  models.py            Request (state, tick_ms, retries, cookies, pre_actions, actions)
  states.py            State ABC + 10 primitives + All(), Any()
  actions.py           Action ABC + 11 built-ins
  reconciler.py        tick-based state evaluation loop
  engine.py            Engine(config, guard=, middleware_state=)
  worker.py            worker_main → persist_context or per-request context
  drivers/playwright.py  launch_browser, open_context (viewport, cookies), navigate, execute_actions
  config.py            WorkerConfig (persist_context, viewport)
  rate_limiter.py      per-domain asyncio.Lock
  cli.py               yoink / yk entrypoints

tests/
  unit/                171 tests
  integration/
    test_engine.py     existing engine tests
    test_bench.py      17 bench tests (auto-skip when stack not running)

bench/  (NOT committed)
  docker-compose.yml
  static/              nginx + 1000 HTML pages
  react/               Vite/React ecommerce SPA
  slow/                Express delay server

scripts/  (NOT committed)
  load_test.py         workers × page_limit sweep
```
