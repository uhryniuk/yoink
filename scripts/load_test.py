#!/usr/bin/env python3
"""Load test harness for yoink — sweeps a workers × page_limit matrix.

Usage:
    uv run python scripts/load_test.py \\
        --url http://localhost:8002/products \\
        --count 100 \\
        --workers 1,2,4,8 \\
        --pages 1,2,5,10 \\
        --timeout 30

Output: one row per config, printed live as each run completes.

    scale  workers  pages  ok    fail  req/s   p50ms  p95ms  p99ms
    -----  -------  -----  ---   ----  -----   -----  -----  -----
    100    1        1      100   0     1.3     780    1100   1340
    ...

Optionally tracks peak RSS via psutil if installed.
"""

from __future__ import annotations

import argparse
import time
from typing import NamedTuple

from yoink import Engine, Request, Selector, load_config

try:
    import psutil

    _PSUTIL = True
except ImportError:
    _PSUTIL = False


class RunResult(NamedTuple):
    scale: int
    workers: int
    pages: int
    n_ok: int
    n_fail: int
    wall_secs: float
    latencies_ms: list[int]
    peak_rss_mb: float | None


def _header() -> str:
    cols = ["scale", "workers", "pages", "ok", "fail", "req/s", "p50ms", "p95ms", "p99ms"]
    if _PSUTIL:
        cols.append("rss_mb")
    return "  ".join(f"{c:>7}" for c in cols)


def _row(r: RunResult) -> str:
    req_s = r.n_ok / r.wall_secs if r.wall_secs > 0 else 0
    lats = sorted(r.latencies_ms)

    def pct(p: float) -> int:
        if not lats:
            return 0
        idx = int(len(lats) * p / 100)
        return lats[min(idx, len(lats) - 1)]

    p50, p95, p99 = pct(50), pct(95), pct(99)
    vals = [r.scale, r.workers, r.pages, r.n_ok, r.n_fail, f"{req_s:.1f}", p50, p95, p99]
    if _PSUTIL:
        rss = f"{r.peak_rss_mb:.0f}" if r.peak_rss_mb else "n/a"
        vals.append(rss)
    return "  ".join(f"{str(v):>7}" for v in vals)


def run_once(
    url: str,
    count: int,
    workers: int,
    pages: int,
    timeout: float,
    state: str | None,
    persist_context: bool = False,
) -> RunResult:
    cfg = load_config()
    cfg.workers.count = workers
    cfg.workers.page_limit = pages
    cfg.workers.persist_context = persist_context

    req_state = Selector(state) if state else None

    reqs = [Request(url=url, timeout=timeout, state=req_state) for _ in range(count)]

    latencies: list[int] = []
    n_ok = 0
    n_fail = 0

    proc = psutil.Process() if _PSUTIL else None
    peak_rss = 0.0

    t_start = time.monotonic()
    with Engine(cfg) as engine:
        for req in reqs:
            engine.submit(req)
        for result in engine.results():
            latencies.append(result.duration_ms)
            if result.ok:
                n_ok += 1
            else:
                n_fail += 1
            if proc:
                rss = proc.memory_info().rss / 1024 / 1024
                if rss > peak_rss:
                    peak_rss = rss
    wall = time.monotonic() - t_start

    return RunResult(
        scale=count,
        workers=workers,
        pages=pages,
        n_ok=n_ok,
        n_fail=n_fail,
        wall_secs=wall,
        latencies_ms=latencies,
        peak_rss_mb=peak_rss if _PSUTIL else None,
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="yoink load test")
    p.add_argument("--url", required=True, help="Target URL")
    p.add_argument("--count", type=int, default=100, help="Number of requests per config")
    p.add_argument("--workers", default="1,2,4", help="Comma-separated worker counts")
    p.add_argument("--pages", default="1,2,5", help="Comma-separated page_limit values")
    p.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout (s)")
    p.add_argument("--state", default=None, help="CSS selector to wait for (optional)")
    p.add_argument("--scales", default=None, help="Comma-separated page counts to sweep (overrides --count)")
    p.add_argument(
        "--persist-context", action="store_true", help="Reuse BrowserContext per worker (faster, less isolated)"
    )
    args = p.parse_args(argv)

    worker_list = [int(x) for x in args.workers.split(",")]
    page_list = [int(x) for x in args.pages.split(",")]
    scales = [int(x) for x in args.scales.split(",")] if args.scales else [args.count]

    print(_header())
    print("-" * (9 * (8 if _PSUTIL else 7)))

    for scale in scales:
        for workers in worker_list:
            for pages in page_list:
                result = run_once(
                    url=args.url,
                    count=scale,
                    workers=workers,
                    pages=pages,
                    timeout=args.timeout,
                    state=args.state,
                    persist_context=args.persist_context,
                )
                print(_row(result), flush=True)


if __name__ == "__main__":
    main()
