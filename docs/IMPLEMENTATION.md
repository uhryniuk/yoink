# Yoink — Implementation Guide

This document is the step-by-step implementation guide for the yoink overhaul. Each step is a discrete unit of work that should be committed individually.

See `ARCHITECTURE.md` for design context.

## Implementation Order

Steps are ordered by dependency. Each step should be fully implemented and committed before moving to the next.

---

### Step 1: `models.py` — Core Data Structures

**File:** `src/yoink/models.py` (new file, replaces nothing)

**What to implement:**

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_factor: float = 2.0
    # Retry on these exception types (referenced by name to avoid circular imports)
    retry_on_scraper_error: bool = True

@dataclass
class ProxyConfig:
    server: str          # "http://host:port"
    username: str | None = None
    password: str | None = None

@dataclass
class Action:
    type: str            # click | setValue | hover | scroll | wait
    selector: str | None = None
    value: str | None = None
    duration_ms: int | None = None  # for scroll/wait

@dataclass
class ExtractReq:
    url: str
    wait_for: str = "networkidle"   # "networkidle" | "domcontentloaded" | CSS selector
    timeout: float = 30.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    proxy: ProxyConfig | None = None
    headers: dict[str, str] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    screenshot: bool = False
    clean_html: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ExtractResult:
    request: ExtractReq
    url: str                        # final URL after redirects
    html: str
    screenshot: bytes | None = None
    duration_ms: int = 0
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

**Also add:** JSON serialization helpers (`to_dict`, `from_dict`) on `ExtractReq` and `ExtractResult` so the service can use them directly.

**Commit:** `feat(models): add ExtractReq, ExtractResult, RetryPolicy, ProxyConfig, Action`

---

### Step 2: `exceptions.py` — Clean Up

**File:** `src/yoink/exceptions.py` (modify existing)

**What to do:**
- Keep the existing exception hierarchy — it's well-designed
- Remove `CliError` (belongs in `cli.py` if needed)
- Ensure all exceptions have brief docstrings
- No new exceptions needed at this step

**Commit:** `chore(exceptions): clean up exception hierarchy, remove CliError`

---

### Step 3: `common.py` — Fix and Trim

**File:** `src/yoink/common.py` (modify existing)

**What to do:**
- Add missing `import json` and `from pathlib import Path`
- Remove LLM-specific utilities: `extract_code_from_funct`, `extract_imports_from_lines`, `extract_before_next_engine`, `extract_next_engine`
- Keep: `clean_html`, `is_valid_url`, `is_valid_html`, `load_urls_from_txt`, `load_urls_from_json`
- Fix any other broken imports

**Commit:** `fix(common): fix missing imports, remove LLM-specific utilities`

---

### Step 4: `config.py` — Configuration System

**File:** `src/yoink/config.py` (new file)

**What to implement:**

```python
from dataclasses import dataclass, field
from multiprocessing import cpu_count

@dataclass
class WorkerConfig:
    count: int = field(default_factory=cpu_count)
    pages_per_worker: int = 5
    idle_timeout_secs: int = 300
    headless: bool = True
    user_agent: str | None = None

@dataclass
class RateLimitConfig:
    default_delay_ms: int = 0
    per_domain: dict[str, int] = field(default_factory=dict)

@dataclass
class ServiceConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str | None = None

@dataclass
class LogConfig:
    level: str = "INFO"
    minimal: bool = False

@dataclass
class Config:
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    log: LogConfig = field(default_factory=LogConfig)
```

**Config loading function:**
```python
def load_config(path: str | None = None) -> Config:
    """Load config: defaults → XDG → path arg → env vars."""
```

Loading order (later wins):
1. Dataclass defaults
2. `~/.config/yoink/config.toml` (XDG base dir)
3. `path` argument if provided
4. `YK_` prefixed env vars (e.g. `YK_WORKERS__COUNT=8`, `YK_SERVICE__API_KEY=secret`)

Use `tomllib` (stdlib, Python ≥ 3.11) for TOML parsing. Double underscore in env var names maps to nested config keys.

**Commit:** `feat(config): add Config hierarchy with TOML, XDG, and env var loading`

---

### Step 5: `logging.py` — Structured Logging

**File:** `src/yoink/logging.py` (new file)

**What to implement:**

```python
import structlog
from yoink.config import LogConfig

def configure_logging(cfg: LogConfig) -> None:
    """Configure structlog for JSONL output to stdout."""
```

- JSONL output: one JSON object per line to stdout
- Standard fields: `timestamp` (ISO 8601), `level`, `event`, plus any bound context
- Minimal mode: only emit `timestamp` and `event` (drop all other fields)
- Level filtering via `cfg.level`

**Commit:** `feat(logging): configure structlog for JSONL output with minimal mode`

---

### Step 6: `drivers/playwright.py` — Async Playwright Driver

**File:** `src/yoink/drivers/playwright.py` (full rewrite)
**File:** `src/yoink/drivers/__init__.py` (clear it)
**Delete:** `src/yoink/drivers/base.py`, `src/yoink/drivers/selenium.py`

**What to implement:**

```python
from playwright.async_api import Browser, Page, BrowserContext
from yoink.models import ExtractReq, Action
from yoink.config import WorkerConfig

async def open_context(browser: Browser, req: ExtractReq) -> BrowserContext:
    """Create an isolated browser context with proxy/headers from req."""

async def navigate(page: Page, req: ExtractReq) -> str:
    """Navigate to req.url, execute actions, wait for stability. Returns final URL."""

async def execute_action(page: Page, action: Action) -> None:
    """Execute a single browser action (click, setValue, hover, scroll, wait)."""

async def wait_for_stable(page: Page, wait_for: str, timeout: float) -> None:
    """Wait for page to reach stable state (networkidle, domcontentloaded, or selector)."""

async def extract_html(page: Page, clean: bool = False) -> str:
    """Extract page HTML, optionally cleaned."""

async def take_screenshot(page: Page) -> bytes:
    """Return PNG screenshot as bytes."""
```

**Keep from existing implementation:**
- DOM stability polling logic
- Network idle via CDP
- iframe context handling
- The JavaScript for clean DOM extraction

**Drop from existing implementation:**
- All YAML/JSON action string parsing (actions are now typed `Action` dataclasses)
- `get_obs()`, `get_possible_interactions()`, `get_capability()` (LLM helpers)
- Screenshot MD5 deduplication
- `find_subclasses()` usage
- `SELENIUM_PROMPT_TEMPLATE` and `DOMNode` references

**Commit:** `feat(drivers): rewrite PlaywrightDriver as async, drop Selenium and LLM helpers`

---

### Step 7: `rate_limiter.py` — Per-Domain Delay

**File:** `src/yoink/rate_limiter.py` (new file)

**What to implement:**

```python
from multiprocessing.managers import DictProxy
from urllib.parse import urlparse
import asyncio
import time

class RateLimiter:
    """Process-safe per-domain delay enforcement."""

    def __init__(self, shared_times: DictProxy, config: RateLimitConfig) -> None:
        self._times = shared_times   # multiprocessing.Manager().dict()
        self._config = config

    def _domain(self, url: str) -> str:
        return urlparse(url).netloc

    def _delay_ms(self, domain: str) -> int:
        return self._config.per_domain.get(domain, self._config.default_delay_ms)

    async def acquire(self, url: str) -> None:
        """Sleep if needed to respect domain delay before making a request."""
        domain = self._domain(url)
        delay = self._delay_ms(domain)
        if delay == 0:
            return
        now = time.monotonic()
        last = self._times.get(domain, 0.0)
        wait = (last + delay / 1000) - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._times[domain] = time.monotonic()
```

**Note on process safety:** `multiprocessing.Manager().dict()` is slow but correct. The lock granularity is per-dict-operation, which is sufficient for per-domain throttling.

**Commit:** `feat(rate_limiter): add process-safe per-domain delay enforcement`

---

### Step 8: `worker.py` — Worker Process

**File:** `src/yoink/worker.py` (new file)

**What to implement:**

```python
import asyncio
from multiprocessing import Queue
from playwright.async_api import async_playwright
from yoink.models import ExtractReq, ExtractResult
from yoink.config import WorkerConfig
from yoink.rate_limiter import RateLimiter
from yoink import drivers

SENTINEL = None  # signals worker to exit

def worker_main(input_q: Queue, output_q: Queue, config: WorkerConfig, rate_limiter: RateLimiter) -> None:
    """Entry point for each worker process. Called after spawn."""
    asyncio.run(_run(input_q, output_q, config, rate_limiter))

async def _run(input_q, output_q, config, rate_limiter):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=config.headless)
        semaphore = asyncio.Semaphore(config.pages_per_worker)
        tasks: set[asyncio.Task] = set()

        loop = asyncio.get_running_loop()
        idle_deadline = loop.time() + config.idle_timeout_secs

        while True:
            try:
                req = await loop.run_in_executor(None, input_q.get, True, 1.0)
            except Exception:
                # Timeout on queue.get — check idle
                if not tasks and loop.time() > idle_deadline:
                    await browser.close()
                    browser = await p.chromium.launch(headless=config.headless)
                    idle_deadline = loop.time() + config.idle_timeout_secs
                continue

            if req is SENTINEL:
                break

            idle_deadline = loop.time() + config.idle_timeout_secs
            await semaphore.acquire()
            task = asyncio.create_task(_fetch(browser, req, output_q, rate_limiter, semaphore))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        if tasks:
            await asyncio.gather(*tasks)
        await browser.close()

async def _fetch(browser, req: ExtractReq, output_q: Queue, rate_limiter: RateLimiter, semaphore) -> None:
    """Fetch one URL with retry. Push ExtractResult to output_q."""
    # Uses tenacity for retry logic based on req.retry
    # Catches all exceptions, wraps in ExtractResult(error=...)
    ...
    semaphore.release()
```

**Commit:** `feat(worker): implement async worker process with Playwright, idle timeout, and retries`

---

### Step 9: `engine.py` — Engine

**File:** `src/yoink/engine.py` (new file, replaces `core.py`)
**Delete:** `src/yoink/core.py`

**What to implement:**

```python
import multiprocessing as mp
from collections.abc import Iterator, Iterable
from yoink.models import ExtractReq, ExtractResult
from yoink.config import Config, load_config
from yoink.worker import worker_main, SENTINEL
from yoink.rate_limiter import RateLimiter

class Engine:
    def __init__(self, config: Config | None = None) -> None:
        self._config = config or load_config()
        self._input_q: mp.Queue | None = None
        self._output_q: mp.Queue | None = None
        self._workers: list[mp.Process] = []
        self._manager: mp.Manager | None = None
        self._submitted = 0
        self._collected = 0

    def __enter__(self) -> "Engine":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.shutdown()

    def start(self) -> None:
        mp.set_start_method("spawn", force=True)
        self._manager = mp.Manager()
        shared_times = self._manager.dict()
        rate_limiter = RateLimiter(shared_times, self._config.rate_limit)

        self._input_q = mp.Queue()
        self._output_q = mp.Queue()

        for _ in range(self._config.workers.count):
            p = mp.Process(
                target=worker_main,
                args=(self._input_q, self._output_q, self._config.workers, rate_limiter),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

    def submit(self, req: str | ExtractReq) -> None:
        if isinstance(req, str):
            req = ExtractReq(url=req)
        self._input_q.put(req)
        self._submitted += 1

    def results(self) -> Iterator[ExtractResult]:
        while self._collected < self._submitted:
            result = self._output_q.get()
            self._collected += 1
            yield result

    def stream(self, reqs: Iterable[str | ExtractReq]) -> Iterator[ExtractResult]:
        for req in reqs:
            self.submit(req)
        yield from self.results()

    def shutdown(self, wait: bool = True) -> None:
        for _ in self._workers:
            self._input_q.put(SENTINEL)
        if wait:
            for w in self._workers:
                w.join()
        self._manager.shutdown()
```

**Commit:** `feat(engine): implement Engine with worker pool, shared queues, and graceful shutdown`

---

### Step 10: `__init__.py` — Public API

**File:** `src/yoink/__init__.py` (rewrite)

**What to expose:**

```python
from yoink.engine import Engine
from yoink.models import ExtractReq, ExtractResult, RetryPolicy, ProxyConfig, Action
from yoink.config import Config, load_config

def get(url: str, **kwargs) -> str:
    """Fetch a single URL. Returns HTML string."""
    req = ExtractReq(url=url, **kwargs)
    with Engine() as engine:
        engine.submit(req)
        return next(engine.results()).html

def get_all(urls: list[str], workers: int | None = None) -> list[ExtractResult]:
    """Fetch multiple URLs in parallel. Returns list of ExtractResult."""
    cfg = load_config()
    if workers:
        cfg.workers.count = workers
    with Engine(cfg) as engine:
        return list(engine.stream(urls))

def stream(urls, workers: int | None = None):
    """Fetch URLs, yielding ExtractResult as each completes."""
    cfg = load_config()
    if workers:
        cfg.workers.count = workers
    with Engine(cfg) as engine:
        yield from engine.stream(urls)

__all__ = [
    "Engine", "ExtractReq", "ExtractResult", "RetryPolicy",
    "ProxyConfig", "Action", "Config", "load_config",
    "get", "get_all", "stream",
]
```

**Commit:** `feat(api): expose public API surface — get, get_all, stream, Engine`

---

### Step 11: `cli.py` — CLI

**File:** `src/yoink/cli.py` (rewrite)

**Entrypoints** (in `pyproject.toml`):
```toml
[project.scripts]
yoink = "yoink.cli:main"
yk = "yoink.cli:main"
```

**Commands:**

```
yoink "https://example.com"            → stdout HTML
yoink urls.txt                         → stdout HTML (one per result, separated)
yoink urls.json                        → same
echo "url" | yoink -                   → stdin support
yoink --stream urls.txt               → JSONL to stdout as results arrive
yoink --workers 4 --pages 5 urls.txt  → configure parallelism
yoink --output ./out/ urls.txt        → write <domain>_<hash>.html per result
yoink --tarball out.tar.gz urls.txt   → write tarball
yoink --config path.toml urls.txt     → use config file
```

Use argparse. JSONL output format for `--stream`:
```json
{"url": "https://...", "ok": true, "duration_ms": 342, "html": "..."}
```

**Commit:** `feat(cli): implement yoink and yk entrypoints with stream and pipe support`

---

### Step 12: `tests/`

**Structure:**
```
tests/
├── conftest.py               # shared fixtures: test config, local HTTP server
├── unit/
│   ├── test_models.py        # ExtractReq/ExtractResult serialization, defaults
│   ├── test_config.py        # TOML loading, env var override, XDG fallback
│   ├── test_rate_limiter.py  # delay enforcement, per-domain config
│   └── test_common.py        # URL validation, HTML cleaning, file loaders
└── integration/
    └── test_engine.py        # real Playwright against local HTTP server
```

**Key fixtures:**
- `local_server` — starts a simple HTTP server serving static HTML for integration tests
- `test_config` — `Config` with `workers.count=1, headless=True`

**Commit:** `test: add unit and integration test suite`

---

### Step 14: `.github/workflows/`

**`ci.yml`** — runs on every PR and push to main:
1. `uv run ruff check src/` — linting
2. `uv run ruff format --check src/` — formatting
3. `uv run mypy src/` — type checking
4. `uv run pytest tests/unit/` — unit tests
5. `uv run pytest tests/integration/` — integration tests (with Playwright browsers installed)

**`release.yml`** — runs on version tags (`v*`):
1. Run CI checks
2. `uv build`
3. Publish to PyPI via `trusted publishing`

**Commit:** `ci: add GitHub Actions workflows for CI and PyPI release`

---

### Step 15: `pyproject.toml` — Dependency Cleanup

**Remove:** `selenium`, `PyYAML`, `python-pyper`

**Keep:** `playwright`, `structlog`, `beautifulsoup4`, `tenacity`

**Dev:** `pytest`, `pytest-cov`, `ruff`, `mypy`

**Entrypoints:**
```toml
[project.scripts]
yoink = "yoink.cli:main"
yk = "yoink.cli:main"
```

**Commit:** `chore(deps): remove selenium/PyYAML/pyper, add fastapi optional extra, update entrypoints`

---

### Step 17: `README.md`

Rewrite with:
- What it is and what it does
- Install: `pip install yoink` / `pipx install yoink`
- Quickstart: one-liner, batch, engine
- CLI usage
- Service usage + Docker
- Configuration reference
- Contributing

**Commit:** `docs: rewrite README with install, quickstart, CLI, service, and config reference`
