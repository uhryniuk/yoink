from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_factor: float = 2.0
    retry_on_scraper_error: bool = True


@dataclass
class ProxyConfig:
    server: str
    username: str | None = None
    password: str | None = None


@dataclass
class Action:
    type: str
    selector: str | None = None
    value: str | None = None
    duration_ms: int | None = None


@dataclass
class ExtractReq:
    url: str
    wait_for: str = "networkidle"
    timeout: float = 30.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    proxy: ProxyConfig | None = None
    headers: dict[str, str] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    screenshot: bool = False
    clean_html: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractReq:
        retry_data = data.pop("retry", {})
        proxy_data = data.pop("proxy", None)
        actions_data = data.pop("actions", [])

        retry = RetryPolicy(**retry_data) if retry_data else RetryPolicy()
        proxy = ProxyConfig(**proxy_data) if proxy_data else None
        actions = [Action(**a) for a in actions_data]

        return cls(retry=retry, proxy=proxy, actions=actions, **data)

    @classmethod
    def from_json(cls, s: str) -> ExtractReq:
        return cls.from_dict(json.loads(s))


@dataclass
class ExtractResult:
    request: ExtractReq
    url: str
    html: str
    screenshot: bytes | None = None
    duration_ms: int = 0
    error: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "html": self.html,
            "screenshot": self.screenshot.hex() if self.screenshot else None,
            "duration_ms": self.duration_ms,
            "error": str(self.error) if self.error else None,
            "ok": self.ok,
            "request": self.request.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
