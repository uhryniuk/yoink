# yoink

Fast, fault-tolerant headless browser scraping. One browser per worker process, N async pages per browser.

```
pip install yoink
pipx install yoink
```

Playwright browsers are required on first run:

```
playwright install chromium
```

---

## CLI

```bash
# Single URL — HTML to stdout
yoink "https://example.com"

# Text file or JSON array of URLs
yoink urls.txt
yoink urls.json

# Stdin
echo "https://example.com" | yoink -

# Stream JSONL results as each page completes
yoink --stream urls.txt

# Write one HTML file per URL to a directory
yoink --output ./results/ urls.txt

# Write a .tar.gz archive
yoink --tarball results.tar.gz urls.txt

# Control parallelism
yoink --workers 4 --pages 10 urls.txt
```

`yk` is an alias for `yoink`.

---

## Python API

```python
import yoink

# One-liner
html = yoink.get("https://example.com")

# Parallel fetch, results in completion order
results = yoink.get_all(["https://a.com", "https://b.com"], workers=4)
for r in results:
    print(r.url, r.ok, len(r.html))

# Stream results as they complete
for result in yoink.stream(urls, workers=4):
    print(result.url, result.ok)

# Engine for full control
with yoink.Engine() as engine:
    engine.submit("https://a.com")
    engine.submit(yoink.ExtractReq(url="https://b.com", screenshot=True, clean_html=True))
    for result in engine.results():
        print(result.html)
        if result.screenshot:
            open("shot.png", "wb").write(result.screenshot)
```

### `ExtractReq` options

| Field | Default | Description |
|---|---|---|
| `url` | required | URL to fetch |
| `wait_for` | `"networkidle"` | `"networkidle"`, `"domcontentloaded"`, or a CSS selector |
| `timeout` | `30.0` | Seconds before giving up |
| `retry` | `RetryPolicy()` | Retry behaviour (see below) |
| `proxy` | `None` | `ProxyConfig(server, username, password)` |
| `headers` | `{}` | Extra request headers |
| `actions` | `[]` | List of `Action` steps to run after page load |
| `screenshot` | `False` | Capture a PNG screenshot (bytes in result) |
| `clean_html` | `False` | Strip `<script>` and `<style>` tags before returning |
| `metadata` | `{}` | Pass-through dict — untouched by yoink |

### `RetryPolicy`

```python
yoink.RetryPolicy(
    max_attempts=3,       # total attempts including the first
    backoff_factor=2.0,   # exponential backoff multiplier
)
```

### `Action` steps

```python
from yoink import Action, ExtractReq

req = ExtractReq(
    url="https://example.com/login",
    actions=[
        Action(type="setValue", selector="#username", value="user@example.com"),
        Action(type="setValue", selector="#password", value="secret"),
        Action(type="click", selector="button[type=submit]"),
        Action(type="wait", selector=".dashboard"),
    ],
)
```

Supported action types: `click`, `setValue`, `setValueAndEnter`, `hover`, `scroll`, `wait`.

---

## Configuration

Config is loaded in this order (later wins):

1. Built-in defaults
2. `~/.config/yoink/config.toml`
3. `--config path/to/config.toml`
4. `YK_` environment variables

### TOML example

```toml
[workers]
count = 4
pages_per_worker = 10
headless = true

[rate_limit]
default_delay_ms = 0

[rate_limit.per_domain]
"news.ycombinator.com" = 1000   # 1 second between requests to this domain
"reddit.com" = 500

[log]
level = "INFO"
minimal = false
```

### Environment variables

```bash
YK_WORKERS__COUNT=8
YK_WORKERS__PAGES_PER_WORKER=10
YK_LOG__LEVEL=DEBUG
YK_LOG__MINIMAL=true
```

Double underscore (`__`) separates section from field.

---

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
pytest

# Run integration tests only (requires Playwright browsers)
pytest tests/integration/

# Lint + format
ruff check .
ruff format .
```
