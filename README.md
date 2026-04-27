# yoink

Fast, fault-tolerant headless browser scraping with built-in bot-detection bypass.

- One Chromium browser per worker process, N async page tabs per browser
- Stealth layer: patches `navigator.webdriver`, `window.chrome`, plugins, WebGL, permissions, and more
- State-based completion: wait for selectors, network idle, DOM stability, HTTP status, or compose your own
- Actions lifecycle: interact with pages before scraping (scroll, click, fill forms, block trackers)
- Auto-installs Playwright Chromium on first run — no manual setup

```bash
pip install python-yoink
```

---

## Quick start

```bash
# Single URL — HTML to stdout
yoink https://example.com

# File of URLs, stream JSONL as each completes
yoink urls.txt --stream

# Save one HTML file per URL
yoink urls.txt --output ./results/

# 4 concurrent pages, save as archive
yoink urls.txt --pages 4 --tarball results.tar.gz
```

`yk` is an alias for `yoink`.

---

## Python API

```python
import yoink

# Single URL
html = yoink.get("https://example.com")

# Wait for a CSS selector before extracting
html = yoink.get("https://shop.example.com", state=yoink.Selector(".product-card"))

# Parallel fetch — results in completion order
results = yoink.get_all(["https://a.com", "https://b.com", "https://c.com"])
for r in results:
    print(r.url, r.status, len(r.html))

# Stream results as they land
for result in yoink.stream(urls, state=yoink.Selector(".content")):
    if result.ok:
        process(result.html)
```

---

## States — when to stop waiting

States define the condition yoink waits for before extracting HTML. They compose with `&` (all) and `|` (any).

```python
from yoink import (
    DOMContentLoaded,   # initial HTML parsed (default)
    NetworkIdle,        # no network requests for 500ms
    DOMStable,          # no DOM mutations for 250ms
    Selector,           # CSS selector present in DOM
    SubstringMatch,     # visible text contains string
    HTTPStatus,         # response status matches
    ResponseHeader,     # response header matches
    MinCount,           # at least N elements match selector
    URLMatches,         # final URL matches pattern
    TimeDelay,          # unconditional wait
    Not,                # logical NOT
    All,                # all states must pass (alias for &)
    Any,                # any state must pass (alias for |)
)

# Wait for selector AND network to go quiet
state = Selector(".results") & NetworkIdle()

# Accept any 2xx status
state = HTTPStatus(lambda s: 200 <= s < 300)

# At least 12 product cards loaded
state = MinCount(".product-card", 12)

# Compose freely
state = (Selector(".data") | TimeDelay(3000)) & Not(SubstringMatch("loading"))
```

---

## Actions — interact before scraping

Actions run against the page. `pre_actions` run before `goto()`, `actions` run after navigation but before state evaluation.

```python
from yoink import Request
from yoink.actions import (
    Click, Fill, Hover, PressKey, SelectOption,
    Scroll, ScrollToBottom,
    Wait, WaitForSelector,
    EvaluateJS,
    RouteBlock,          # block URLs matching patterns (ads, trackers)
)

req = Request(
    url="https://shop.example.com",
    pre_actions=[
        RouteBlock("**/ads/**", "**/analytics/**", "**doubleclick**"),
    ],
    actions=[
        WaitForSelector(".product-grid"),
        ScrollToBottom(step_px=400, delay_ms=80),
        Click(".load-more"),
    ],
    state=MinCount(".product-card", 20),
    retries=2,
)

results = yoink.get_all([req])
```

---

## Engine — full control

```python
from yoink import Engine, Config, load_config
from yoink import HTTPStatus, Not, SubstringMatch, DOMStable

cfg = load_config()
cfg.workers.count = 2
cfg.workers.page_limit = 6

with Engine(
    config=cfg,
    guard=HTTPStatus(200) & Not(SubstringMatch("captcha")),  # fail fast on blocked pages
    middleware_state=DOMStable(),                              # applied to every request
) as engine:
    for url in urls:
        engine.submit(Request(url=url, retries=2, timeout=20))

    for result in engine.results():
        if result.ok:
            save(result.html)
        elif result.terminal == "guard_failed":
            handle_block(result.url)
        elif result.terminal == "timeout":
            retry_later(result.url)
```

### Result fields

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | `True` when `terminal == "success"` |
| `html` | `str` | Extracted page HTML |
| `url` | `str` | Final URL after redirects |
| `status` | `int\|None` | HTTP response status |
| `headers` | `dict` | Response headers |
| `terminal` | `str` | `"success"`, `"timeout"`, `"error"`, `"guard_failed"` |
| `duration_ms` | `int` | Total wall time including retries |
| `screenshot` | `bytes\|None` | PNG bytes if `screenshot=True` |
| `error` | `Exception\|None` | Exception on error terminal |

---

## Request options

```python
Request(
    url="https://example.com",
    state=None,               # State | None — completion condition
    timeout=30.0,             # seconds before terminal="timeout"
    retries=0,                # retry count on error or timeout
    tick_ms=250,              # reconciler poll interval (ms)
    headers={},               # extra request headers
    cookies={},               # injected as Cookie header
    proxy=None,               # ProxyConfig(server, username, password)
    pre_actions=[],           # actions before goto()
    actions=[],               # actions after goto(), before state eval
    screenshot=False,         # capture PNG screenshot
    clean_html=False,         # strip <script>/<style>/<svg> tags
    use_browser=True,         # False → httpx fast path (no JS, no actions)
    metadata={},              # pass-through dict, untouched
)
```

---

## Stealth

Every browser context is patched before any page script runs:

| Signal | Patch |
|---|---|
| `navigator.webdriver` | `undefined` (not `true`) |
| `window.chrome` | Full runtime/app/csi object |
| `navigator.plugins` | 5 PDF Viewer plugins |
| `navigator.mimeTypes` | PDF mime types |
| `navigator.languages` | `['en-US', 'en']` |
| `navigator.deviceMemory` | `8` |
| `navigator.userAgentData` | Chrome 124 brand list |
| WebGL vendor/renderer | `Intel Inc. / Intel Iris OpenGL Engine` |
| `Notification.permission` | `'default'` (not `'denied'`) |
| `Function.prototype.toString` | Native code appearance |

The `--disable-blink-features=AutomationControlled` Chromium flag is also set, which removes the automation infobar and additional blink-level automation signals.

---

## Performance

Rule of thumb: **1 worker per machine, `page_limit = cpu_cores / 2`**.

Each worker is one Chromium browser (a heavy multi-process application). Adding more workers means more competing browsers on the same CPU. Pages are cheap async tasks within one browser and scale well for network-bound targets.

```
workers  pages   req/s   p50ms   notes
1        1       3.1     306     sequential
1        4       9.4     336     async concurrency kicks in
1        8       11.9    506     approaching CPU saturation
2        4       10.7    483     two browsers compete, worse than 1×8
4        4       11.2    804     p50 triples vs 1×4
```

*Benchmarked against a local server with 200ms simulated latency.*

To scale beyond a single machine: run multiple yoink processes on separate hosts pointing at the same external work queue.

For non-JS pages, `use_browser=False` routes through `httpx` (no Chromium overhead):

```python
req = Request(url="https://api.example.com/feed.json", use_browser=False)
```

---

## Configuration

Config is loaded in order (later wins): defaults → `~/.config/yoink/config.toml` → `--config FILE` → `YK_` env vars.

```toml
[workers]
count = 1               # workers per machine (default: 1)
page_limit = 4          # concurrent pages per worker (default: cpu_count // 2)
headless = true
idle_timeout_secs = 300
persist_context = false # reuse one BrowserContext per worker (faster, less isolated)

[rate_limit]
default_delay_ms = 0

[rate_limit.per_domain]
"news.ycombinator.com" = 1000
"reddit.com" = 500

[log]
level = "INFO"
```

Environment variables use `YK_SECTION__FIELD` (double underscore):

```bash
YK_WORKERS__COUNT=2
YK_WORKERS__PAGE_LIMIT=6
YK_RATE_LIMIT__DEFAULT_DELAY_MS=500
YK_LOG__LEVEL=DEBUG
```

---

## Docker

```bash
docker build -t yoink .
docker run --rm yoink https://example.com
docker run --rm yoink --stream --pages 4 - < urls.txt
```

---

## Development

```bash
uv sync
uv run pytest tests/unit/         # 179 unit tests, no browser needed
uv run pytest tests/integration/  # requires Playwright Chromium
```
