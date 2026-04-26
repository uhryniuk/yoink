"""Production pipeline pattern — guard + middleware_state, streaming JSONL output.

Reads URLs from argv or stdin, one per line. Outputs one JSON object per result.

Usage:
    echo "https://example.com" | uv run python examples/engine_pipeline.py
    uv run python examples/engine_pipeline.py urls/sample.txt
    uv run python examples/engine_pipeline.py https://example.com https://example.org
"""

from __future__ import annotations

import json
import sys

import yoink
from yoink import Engine, HTTPStatus, NetworkIdle, Request, Selector, load_config
from yoink.common import is_valid_url


def load_urls(args: list[str]) -> list[str]:
    if not args:
        return [line.strip() for line in sys.stdin if line.strip()]

    urls = []
    for arg in args:
        from pathlib import Path
        p = Path(arg)
        if p.exists():
            urls.extend(line.strip() for line in p.read_text().splitlines() if line.strip())
        elif is_valid_url(arg):
            urls.append(arg)
    return [u for u in urls if is_valid_url(u)]


def run(urls: list[str]) -> None:
    cfg = load_config()
    cfg.workers.count = 2
    cfg.workers.page_limit = 4

    guard = HTTPStatus(lambda s: 200 <= s < 400)
    middleware = NetworkIdle()

    reqs = [Request(url=u, clean_html=True, state=Selector("body")) for u in urls]

    with Engine(cfg, guard=guard, middleware_state=middleware) as engine:
        for req in reqs:
            engine.submit(req)
        for result in engine.results():
            row = {
                "url": result.url,
                "ok": result.ok,
                "status": result.status,
                "terminal": result.terminal,
                "duration_ms": result.duration_ms,
                "bytes": len(result.html) if result.html else 0,
                "error": str(result.error) if result.error else None,
            }
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    urls = load_urls(sys.argv[1:])
    if not urls:
        print("No valid URLs found. Pass URLs as args or pipe via stdin.", file=sys.stderr)
        sys.exit(1)
    run(urls)
