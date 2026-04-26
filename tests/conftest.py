"""Shared fixtures across unit and integration tests."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from yoink.config import Config, RateLimitConfig, WorkerConfig


# ---------------------------------------------------------------------------
# Local HTTP server
# ---------------------------------------------------------------------------

_HTML = b"""<!DOCTYPE html>
<html>
<head><title>Yoink Test</title></head>
<body>
  <h1 id="heading">Yoink Test Page</h1>
  <p>Some content here.</p>
  <script>console.log("loaded")</script>
  <style>body { color: red; }</style>
  <a href="/">home</a>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_HTML)

    def log_message(self, *_):
        pass  # silence request logs during tests


@pytest.fixture(scope="session")
def local_server() -> str:
    """Start a local HTTP server for the test session. Returns the base URL."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)  # port=0 → OS picks a free port
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def test_config() -> Config:
    """Minimal Config suitable for tests — 1 worker, headless."""
    return Config(
        workers=WorkerConfig(count=1, page_limit=2, headless=True),
        rate_limit=RateLimitConfig(),
    )
