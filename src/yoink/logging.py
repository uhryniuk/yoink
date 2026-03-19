from __future__ import annotations

import logging
import sys

import structlog

from yoink.config import LogConfig


def configure_logging(cfg: LogConfig) -> None:
    """Configure structlog to emit JSONL to stdout.

    Normal mode emits all bound context fields::

        {"timestamp": "...", "level": "info", "event": "page fetched", "url": "...", "duration_ms": 342}

    Minimal mode (``cfg.minimal = True``) drops everything except timestamp
    and event, useful for human-readable tailing::

        {"timestamp": "...", "event": "page fetched"}
    """
    level = getattr(logging, cfg.level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if cfg.minimal:
        shared_processors.append(_drop_all_but_timestamp_and_event)

    shared_processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Silence the stdlib root logger so we don't get duplicate output
    logging.basicConfig(level=level, handlers=[logging.NullHandler()])


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a structlog logger, optionally bound to a name."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger=name)
    return logger


# -- processors ---------------------------------------------------------------


def _drop_all_but_timestamp_and_event(
    logger: object,
    method: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Minimal mode: keep only timestamp and event."""
    return {
        "timestamp": event_dict.get("timestamp"),
        "event": event_dict.get("event"),
    }
