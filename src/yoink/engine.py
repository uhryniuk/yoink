"""Engine: manages the worker pool and coordinates input/output queues."""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Iterable, Iterator

from yoink.config import Config, load_config
from yoink.models import ExtractReq, ExtractResult
from yoink.rate_limiter import RateLimiter
from yoink.worker import SENTINEL, worker_main


class Engine:
    """Manages a pool of Playwright worker processes for parallel scraping.

    Use as a context manager::

        with Engine() as engine:
            engine.submit("https://a.com")
            engine.submit("https://b.com")
            for result in engine.results():
                print(result.html)

    Or submit and stream in one call::

        for result in Engine().stream(urls):
            print(result.url, result.ok)
    """

    def __init__(self, config: Config | None = None) -> None:
        self._config = config or load_config()
        self._input_q: mp.Queue | None = None
        self._output_q: mp.Queue | None = None
        self._workers: list[mp.Process] = []
        self._manager: mp.managers.SyncManager | None = None
        self._submitted: int = 0
        self._collected: int = 0
        self._started: bool = False

    # -- context manager ------------------------------------------------------

    def __enter__(self) -> Engine:
        self.start()
        return self

    def __exit__(self, *_) -> None:
        self.shutdown()

    # -- public API -----------------------------------------------------------

    def start(self) -> None:
        """Start worker processes. Called automatically by the context manager."""
        if self._started:
            return

        # spawn avoids forking a process that already holds Playwright state
        ctx = mp.get_context("spawn")

        self._manager = ctx.Manager()
        shared_times = self._manager.dict()
        rate_limiter = RateLimiter(shared_times, self._config.rate_limit)

        self._input_q = ctx.Queue()
        self._output_q = ctx.Queue()

        for _ in range(self._config.workers.count):
            p = ctx.Process(
                target=worker_main,
                args=(self._input_q, self._output_q, self._config.workers, rate_limiter),
                daemon=True,
            )
            p.start()
            self._workers.append(p)

        self._started = True

    def submit(self, req: str | ExtractReq) -> None:
        """Add a URL or ExtractReq to the work queue."""
        if not self._started:
            self.start()
        if isinstance(req, str):
            req = ExtractReq(url=req)
        self._input_q.put(req)
        self._submitted += 1

    def results(self) -> Iterator[ExtractResult]:
        """Yield results as they arrive. Blocks until all submitted work is collected."""
        while self._collected < self._submitted:
            yield self._output_q.get()
            self._collected += 1

    def stream(self, reqs: Iterable[str | ExtractReq]) -> Iterator[ExtractResult]:
        """Submit all requests then yield results as they complete."""
        if not self._started:
            self.start()
        for req in reqs:
            self.submit(req)
        yield from self.results()

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully stop all workers and release resources.

        Sends a sentinel to each worker so they finish in-flight work before
        exiting. Set ``wait=False`` to skip joining (e.g. in tests or signals).
        """
        if not self._started:
            return

        for _ in self._workers:
            self._input_q.put(SENTINEL)

        if wait:
            for w in self._workers:
                w.join(timeout=30)

        for w in self._workers:
            if w.is_alive():
                w.terminate()

        self._workers.clear()
        self._manager.shutdown()
        self._started = False
