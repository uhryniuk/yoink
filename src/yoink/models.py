from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from yoink.states import TICK_MS

if TYPE_CHECKING:
    from yoink.actions import Action
    from yoink.states import State


@dataclass
class ProxyConfig:
    server: str
    username: str | None = None
    password: str | None = None


@dataclass
class Request:
    url: str
    timeout: float = 30.0
    proxy: ProxyConfig | None = None
    headers: dict[str, str] = field(default_factory=dict)
    screenshot: bool = False
    clean_html: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    state: State | None = field(default=None, repr=False)
    tick_ms: int = TICK_MS
    retries: int = 0
    cookies: dict[str, str] = field(default_factory=dict)
    pre_actions: list[Action] = field(default_factory=list, repr=False)
    actions: list[Action] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "timeout": self.timeout,
            "proxy": dataclasses.asdict(self.proxy) if self.proxy else None,
            "headers": self.headers,
            "screenshot": self.screenshot,
            "clean_html": self.clean_html,
            "metadata": self.metadata,
            "tick_ms": self.tick_ms,
            "retries": self.retries,
            "cookies": self.cookies,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Request:
        data = dict(data)
        proxy_data = data.pop("proxy", None)
        proxy = ProxyConfig(**proxy_data) if proxy_data else None
        return cls(proxy=proxy, **data)

    @classmethod
    def from_json(cls, s: str) -> Request:
        return cls.from_dict(json.loads(s))


@dataclass
class Result:
    request: Request
    url: str
    html: str
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    screenshot: bytes | None = None
    duration_ms: int = 0
    terminal: str = "success"
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.terminal == "success"

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "html": self.html,
            "status": self.status,
            "headers": self.headers,
            "screenshot": self.screenshot.hex() if self.screenshot else None,
            "duration_ms": self.duration_ms,
            "terminal": self.terminal,
            "ok": self.ok,
            "error": str(self.error) if self.error else None,
            "request": self.request.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
