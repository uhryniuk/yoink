"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI

from yoink.config import Config, load_config
from yoink.engine import Engine
from yoink.models import ExtractReq, ExtractResult
from yoink.service.auth import ApiKeyMiddleware
from yoink.service.routes import router


class EngineRouter:
    """Routes ExtractResults back to the correct waiting request via asyncio Futures."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._pending: dict[str, asyncio.Future[ExtractResult]] = {}
        self._drain_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._engine.start()
        self._drain_task = asyncio.create_task(self._drain())

    async def stop(self) -> None:
        if self._drain_task:
            self._drain_task.cancel()
            # Unblock any thread stuck on output_q.get so it can see the cancel
            try:
                self._engine._output_q.put_nowait(None)
            except Exception:
                pass
        self._engine.shutdown(wait=False)

    async def fetch(self, req: ExtractReq) -> ExtractResult:
        """Submit a request and await its specific result."""
        request_id = req.metadata.get("_request_id") or str(uuid.uuid4())
        req.metadata["_request_id"] = request_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[ExtractResult] = loop.create_future()
        self._pending[request_id] = fut

        self._engine.submit(req)
        return await fut

    async def _drain(self) -> None:
        """Pull results from the engine output queue and route to waiting futures."""
        loop = asyncio.get_running_loop()
        while True:
            try:
                # Use a timeout so the thread unblocks regularly and can
                # notice cancellation promptly on shutdown.
                result: ExtractResult | None = await loop.run_in_executor(
                    None, lambda: self._engine._output_q.get(timeout=1.0)
                )
                if result is None:  # shutdown sentinel
                    break
                request_id = result.request.metadata.get("_request_id")
                fut = self._pending.pop(request_id, None)
                if fut and not fut.done():
                    fut.set_result(result)
            except asyncio.CancelledError:
                break
            except Exception:
                continue  # queue.Empty on timeout — loop and try again


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = Engine(cfg)
        engine_router = EngineRouter(engine)
        await engine_router.start()

        app.state.config = cfg
        app.state.engine = engine
        app.state.engine_router = engine_router
        app.state.stats = {
            "started_at": time.monotonic(),
            "total_processed": 0,
            "total_duration_ms": 0,
        }

        yield

        await engine_router.stop()

    app = FastAPI(
        title="yoink",
        version="0.1.0",
        description="Headless browser scraping service.",
        lifespan=lifespan,
    )
    app.add_middleware(ApiKeyMiddleware, api_key=cfg.service.api_key)
    app.include_router(router)

    return app
