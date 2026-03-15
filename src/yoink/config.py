from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any

_ENV_PREFIX = "YK_"
_XDG_CONFIG = Path.home() / ".config" / "yoink" / "config.toml"

# Maps uppercase env var section name → (Config attribute name, nested dataclass type)
_SECTIONS: dict[str, tuple[str, type]] = {
    "WORKERS": ("workers", None),      # filled after class definitions
    "RATE_LIMIT": ("rate_limit", None),
    "SERVICE": ("service", None),
    "LOG": ("log", None),
}


@dataclass
class WorkerConfig:
    count: int = field(default_factory=cpu_count)
    pages_per_worker: int = 5
    idle_timeout_secs: int = 300
    headless: bool = True
    user_agent: str | None = None


@dataclass
class RateLimitConfig:
    default_delay_ms: int = 0
    per_domain: dict[str, int] = field(default_factory=dict)


@dataclass
class ServiceConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str | None = None


@dataclass
class LogConfig:
    level: str = "INFO"
    minimal: bool = False


@dataclass
class Config:
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    log: LogConfig = field(default_factory=LogConfig)


# Fill in class references now that they're defined
_SECTIONS["WORKERS"] = ("workers", WorkerConfig)
_SECTIONS["RATE_LIMIT"] = ("rate_limit", RateLimitConfig)
_SECTIONS["SERVICE"] = ("service", ServiceConfig)
_SECTIONS["LOG"] = ("log", LogConfig)

# Maps TOML section key → same structure (lowercase)
_TOML_SECTIONS: dict[str, tuple[str, type]] = {k.lower(): v for k, v in _SECTIONS.items()}


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration with layered precedence.

    Layers (later wins):
    1. Dataclass defaults
    2. XDG config: ``~/.config/yoink/config.toml``
    3. ``path`` argument if provided
    4. ``YK_`` env vars (e.g. ``YK_WORKERS__COUNT=8``)

    Env var format: ``YK_<SECTION>__<FIELD>`` using uppercase and double
    underscore as the section separator. Example::

        YK_WORKERS__COUNT=4
        YK_SERVICE__API_KEY=secret
        YK_RATE_LIMIT__DEFAULT_DELAY_MS=500
        YK_LOG__LEVEL=DEBUG
    """
    config = Config()

    if _XDG_CONFIG.exists():
        _apply_toml(config, _load_toml(_XDG_CONFIG))

    if path is not None:
        _apply_toml(config, _load_toml(Path(path)))

    _apply_env(config)

    return config


# -- internals ----------------------------------------------------------------


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _apply_toml(config: Config, data: dict[str, Any]) -> None:
    """Merge a parsed TOML dict into config in-place."""
    for section, (attr, _) in _TOML_SECTIONS.items():
        if section not in data:
            continue
        obj = getattr(config, attr)
        for key, value in data[section].items():
            if hasattr(obj, key):
                setattr(obj, key, value)


def _apply_env(config: Config) -> None:
    """Apply YK_SECTION__FIELD env vars to config in-place."""
    for raw_key, value in os.environ.items():
        if not raw_key.startswith(_ENV_PREFIX):
            continue
        rest = raw_key[len(_ENV_PREFIX):]
        if "__" not in rest:
            continue

        section, field_name = rest.split("__", 1)
        field_name = field_name.lower()

        if section not in _SECTIONS:
            continue

        attr, _ = _SECTIONS[section]
        obj = getattr(config, attr)

        if not hasattr(obj, field_name):
            continue

        setattr(obj, field_name, _coerce(value, getattr(obj, field_name)))


def _coerce(value: str, current: Any) -> Any:
    """Coerce an env var string to match the type of the existing field value."""
    if isinstance(current, bool):
        return value.lower() in ("true", "1", "yes")
    if isinstance(current, int):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value  # str, str | None — pass through as-is
