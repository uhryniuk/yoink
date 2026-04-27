"""CLI entrypoints for yoink and yk."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import yoink
from yoink.common import is_valid_url, load_urls_from_json, load_urls_from_txt
from yoink.config import load_config
from yoink.models import Request, Result

# -- playwright auto-install --------------------------------------------------


def _ensure_playwright_browsers() -> None:
    """Ensure the Playwright Chromium build for this playwright version is present.

    Runs ``playwright install chromium`` unconditionally — it exits quickly when
    the correct version is already cached, so it's safe to call on every startup.
    """
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        print("error: playwright install failed", file=sys.stderr)
        sys.exit(1)


# -- input parsing ------------------------------------------------------------


def _load_input(source: str) -> list[str]:
    """Resolve a URL, file path, or '-' (stdin) to a list of URLs."""
    if source == "-":
        return [line.strip() for line in sys.stdin if line.strip() and is_valid_url(line.strip())]

    path = Path(source)
    if path.exists() and path.is_file():
        if path.suffix == ".json":
            urls = load_urls_from_json(path)
        else:
            urls = load_urls_from_txt(path)
        # Validate file-sourced URLs the same way we validate stdin
        return [u for u in urls if is_valid_url(u)]

    if is_valid_url(source):
        return [source]

    print(f"error: cannot read URLs from {source!r}", file=sys.stderr)
    sys.exit(1)


# -- output helpers -----------------------------------------------------------


def _result_filename(url: str) -> str:
    """Stable filename for a URL: <domain>_<hash8>.html"""
    domain = urlparse(url).netloc.replace(".", "_")
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{domain}_{digest}.html"


def _result_to_jsonl(result: Result) -> str:
    return json.dumps(
        {
            "url": result.url,
            "ok": result.ok,
            "status": result.status,
            "terminal": result.terminal,
            "duration_ms": result.duration_ms,
            "error": str(result.error) if result.error else None,
            "html": result.html,
        }
    )


def _write_to_dir(results: list[Result], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for r in results:
        if not r.ok:
            continue
        out = directory / _result_filename(r.url)
        out.write_text(r.html, encoding="utf-8")
        print(f"  wrote {out}", file=sys.stderr)


def _write_tarball(results: list[Result], tarball: Path) -> None:
    with tarfile.open(tarball, "w:gz") as tf:
        for r in results:
            if not r.ok:
                continue
            name = _result_filename(r.url)
            data = r.html.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, BytesIO(data))
    print(f"wrote {tarball}", file=sys.stderr)


# -- subcommands --------------------------------------------------------------


def _cmd_scrape(args: argparse.Namespace) -> int:
    urls = _load_input(args.input)
    if not urls:
        print("no URLs found in input", file=sys.stderr)
        return 0

    cfg = load_config(args.config)
    # CLI defaults: sync mode
    if args.workers is None:
        cfg.workers.count = 1
    else:
        cfg.workers.count = args.workers
    if args.pages is None:
        cfg.workers.page_limit = 1
    else:
        cfg.workers.page_limit = args.pages

    reqs = [Request(url=u) for u in urls]

    # -- streaming JSONL mode -------------------------------------------------
    if args.stream:
        with yoink.Engine(cfg) as engine:
            for req in reqs:
                engine.submit(req)
            for result in engine.results():
                print(_result_to_jsonl(result), flush=True)
        return 0

    # -- collect all results --------------------------------------------------
    with yoink.Engine(cfg) as engine:
        results = list(engine.stream(reqs))

    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]

    if fail:
        for r in fail:
            print(f"error: {r.url}: {r.error}", file=sys.stderr)

    # Output routing
    if args.output:
        _write_to_dir(results, Path(args.output))
    elif args.tarball:
        _write_tarball(results, Path(args.tarball))
    else:
        for r in ok:
            print(r.html)
            if len(ok) > 1:
                print()

    return 0 if not fail else 1


# -- parsers ------------------------------------------------------------------


def _scrape_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="yoink",
        description="Fast headless browser scraping at scale.",
    )
    p.add_argument("--version", action="version", version=f"yoink {yoink.__version__}")
    p.add_argument("input", nargs="?", metavar="INPUT", help="URL, path to .txt/.json file, or '-' for stdin")
    p.add_argument("--config", metavar="FILE", default=None, help="Path to TOML config file")
    p.add_argument("--workers", "-w", type=int, default=None, help="Number of worker processes (default: 1)")
    p.add_argument("--pages", "-p", type=int, default=None, help="Concurrent pages per worker (default: 1)")
    p.add_argument("--stream", "-s", action="store_true", help="Emit JSONL results to stdout as each completes")
    p.add_argument("--output", "-o", metavar="DIR", help="Write HTML files to this directory")
    p.add_argument("--tarball", "-t", metavar="FILE", help="Write results as a .tar.gz archive")
    return p


def main(argv: list[str] | None = None) -> int:
    args_list = sys.argv[1:] if argv is None else list(argv)

    parser = _scrape_parser()
    args = parser.parse_args(args_list)

    if not args.input:
        parser.print_help()
        return 0

    _ensure_playwright_browsers()
    return _cmd_scrape(args)


if __name__ == "__main__":
    sys.exit(main())
