"""Route handlers: /extract, /extract/batch, /config, /status, /health."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from yoink.models import (
    Action, ExtractReq, ExtractResult, ProxyConfig, RetryPolicy,
)
from yoink.service.models import ExtractReqModel, ExtractResultModel

router = APIRouter()


# -- converters ---------------------------------------------------------------


def _to_extract_req(model: ExtractReqModel, request_id: str | None = None) -> ExtractReq:
    meta = dict(model.metadata)
    if request_id:
        meta["_request_id"] = request_id
    return ExtractReq(
        url=model.url,
        wait_for=model.wait_for,
        timeout=model.timeout,
        retry=RetryPolicy(
            max_attempts=model.retry.max_attempts,
            backoff_factor=model.retry.backoff_factor,
            retry_on_scraper_error=model.retry.retry_on_scraper_error,
        ),
        proxy=ProxyConfig(**model.proxy.model_dump()) if model.proxy else None,
        headers=model.headers,
        actions=[Action(**a.model_dump()) for a in model.actions],
        screenshot=model.screenshot,
        clean_html=model.clean_html,
        metadata=meta,
    )


def _to_result_model(result: ExtractResult) -> ExtractResultModel:
    req = result.request
    return ExtractResultModel(
        url=result.url,
        ok=result.ok,
        html=result.html,
        screenshot=result.screenshot.hex() if result.screenshot else None,
        duration_ms=result.duration_ms,
        error=str(result.error) if result.error else None,
        request=ExtractReqModel(
            url=req.url,
            wait_for=req.wait_for,
            timeout=req.timeout,
            headers=req.headers,
            screenshot=req.screenshot,
            clean_html=req.clean_html,
            metadata={k: v for k, v in req.metadata.items() if not k.startswith("_")},
        ),
    )


# -- routes -------------------------------------------------------------------


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/config")
async def config(request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    return {
        "workers": {
            "count": cfg.workers.count,
            "pages_per_worker": cfg.workers.pages_per_worker,
            "idle_timeout_secs": cfg.workers.idle_timeout_secs,
            "headless": cfg.workers.headless,
        },
        "rate_limit": {
            "default_delay_ms": cfg.rate_limit.default_delay_ms,
            "per_domain": cfg.rate_limit.per_domain,
        },
        "service": {
            "host": cfg.service.host,
            "port": cfg.service.port,
            "api_key": "***" if cfg.service.api_key else None,
        },
        "log": {
            "level": cfg.log.level,
            "minimal": cfg.log.minimal,
        },
    }


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    state = request.app.state
    stats = state.stats
    total = stats["total_processed"]
    total_ms = stats["total_duration_ms"]
    return {
        "workers": state.config.workers.count,
        "queue_size": state.engine._input_q.qsize() if state.engine._input_q else 0,
        "total_processed": total,
        "avg_duration_ms": round(total_ms / total) if total else 0,
        "uptime_secs": round(time.monotonic() - stats["started_at"]),
    }


@router.post("/extract")
async def extract(body: ExtractReqModel, request: Request) -> ExtractResultModel:
    router_state = request.app.state
    request_id = str(uuid.uuid4())
    req = _to_extract_req(body, request_id)
    result = await router_state.engine_router.fetch(req)
    _record_stats(request.app.state, result)
    return _to_result_model(result)


@router.post("/extract/batch")
async def extract_batch(
    body: list[ExtractReqModel],
    request: Request,
) -> StreamingResponse:
    engine_router = request.app.state.engine_router
    app_state = request.app.state

    reqs = [_to_extract_req(m, str(uuid.uuid4())) for m in body]

    async def _stream() -> AsyncIterator[str]:
        tasks = [asyncio.create_task(engine_router.fetch(req)) for req in reqs]
        for coro in asyncio.as_completed(tasks):
            result = await coro
            _record_stats(app_state, result)
            yield json.dumps(_to_result_model(result).model_dump()) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


def _record_stats(state: Any, result: ExtractResult) -> None:
    state.stats["total_processed"] += 1
    state.stats["total_duration_ms"] += result.duration_ms
