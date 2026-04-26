from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any


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

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Request:
        # Don't mutate the caller's dict
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
