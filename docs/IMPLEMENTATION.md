# Yoink — Implementation Plan

Feature sets are listed in dependency order. Each builds on the previous.
See `ARCHITECTURE.md` for design context and `FUTURE.md` for original vision.

---

## FS-1: Core Data Layer
**Files:** `models.py`, `exceptions.py`, `common.py`
**Depends on:** nothing

The foundation. Everything else imports from here.

- `models.py` — `ExtractReq` → `Request`, `ExtractResult` → `Result`. Add `status`, `headers`, `terminal` to Result. Remove `Action`. Fix `from_dict` (use `.get()` not `.pop()`).
- `exceptions.py` — gut to three: `YoinkError`, `TimeoutError`, `NavigationError`. Current hierarchy is unused noise.
- `common.py` — rewrite `clean_html` with BeautifulSoup (already a dep, currently only used for the always-true `is_valid_html`). Regex approach breaks on nested tags.

---

## FS-2: State System
**Files:** `states.py` (new)
**Depends on:** nothing (pure Python + Playwright types)

The core abstraction. This is what makes the library worth using.

- `State` ABC with `async def check(page, response) -> bool`
- `__and__` → `AllState` (sequential: left must resolve before right starts)
- `__or__` → `AnyState` (concurrent: both tick, first True wins)
- `Not(state)` — negation wrapper
- `TICK_MS = 250` module constant
- Primitives: `DOMContentLoaded`, `NetworkIdle`, `DOMStable`, `Selector`, `SubstringMatch`, `TimeDelay`, `HTTPStatus`, `ResponseHeader`, `URLMatches`

---

## FS-3: Reconciler
**Files:** `reconciler.py` (new), `drivers/playwright.py`
**Depends on:** FS-1, FS-2

The execution engine that drives a State against a live page.

- `reconciler.py` — tick loop at `tick_ms` intervals. Handles `AllState` (sequential), `AnyState` (concurrent via asyncio tasks), timeout, retries (`int` or tenacity `Retrying`). Returns terminal: `"success"`, `"timeout"`, `"error"`.
- `drivers/playwright.py` — update `navigate()` to capture and return `Response`. Remove `wait_for_stable`, `execute_action`, `_JS_WAIT_DOM_STABLE`. Keep browser launch and context management.

---

## FS-4: Worker & Rate Limiter
**Files:** `worker.py`, `rate_limiter.py`
**Depends on:** FS-3

The worker process — drives the reconciler, manages the browser lifecycle.

- `worker.py` — replace raw `wait_for` with reconciler call. Fix idle timeout: browser stays closed after idle, reopens lazily when next request arrives (not immediately). Rename `pages_per_worker` → `page_limit`.
- `rate_limiter.py` — fix TOCTOU race: wrap read-sleep-write in a per-domain `asyncio.Lock`.

---

## FS-5: Engine
**Files:** `engine.py`, `config.py`
**Depends on:** FS-4

The coordinator — worker pool, queues, middleware.

- `engine.py` — add `guard: State | None` and `middleware_state: State | None` params. `guard` is evaluated instantly from the HTTP response, fails fast with `terminal="guard_failed"`. `middleware_state` is AND'd into every request's state before reconciler runs. Update `submit()` for new `Request` type.
- `config.py` — rename `pages_per_worker` → `page_limit` throughout.

---

## FS-6: Public API & CLI
**Files:** `__init__.py`, `cli.py`
**Depends on:** FS-5

The surface users actually touch.

- `__init__.py` — update `get`, `get_all`, `stream` to accept `state=` kwarg (default `DOMContentLoaded()`), `retries=`, `tick_ms=`. `Engine` gets no defaults — caller must configure. `get`/`get_all`/`stream` apply opinionated defaults.
- `cli.py` — default `workers=1, page_limit=1` (sync mode). Validate URLs from txt/json files (same as stdin). Fix `_write_to_dir` and `_write_tarball` to skip failed results. Update JSONL output for new `Result` shape.

---

## FS-7: Tests
**Files:** `tests/`
**Depends on:** FS-1 through FS-6

- Unit: `test_states.py` — composition, tick logic, AllState/AnyState/Not behaviour
- Unit: `test_reconciler.py` — success, timeout, retry, guard_failed terminals
- Unit: `test_models.py` — Request/Result serialisation, from_dict non-mutation
- Unit: `test_rate_limiter.py` — update for lock fix
- Integration: `test_engine.py` — real Playwright, guard, middleware_state, retries
