"""Pydantic request/response models for the service layer."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ActionModel(BaseModel):
    type: str
    selector: str | None = None
    value: str | None = None
    duration_ms: int | None = None


class RetryPolicyModel(BaseModel):
    max_attempts: int = 3
    backoff_factor: float = 2.0
    retry_on_scraper_error: bool = True


class ProxyConfigModel(BaseModel):
    server: str
    username: str | None = None
    password: str | None = None


class ExtractReqModel(BaseModel):
    url: str
    wait_for: str = "networkidle"
    timeout: float = 30.0
    retry: RetryPolicyModel = Field(default_factory=RetryPolicyModel)
    proxy: ProxyConfigModel | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    actions: list[ActionModel] = Field(default_factory=list)
    screenshot: bool = False
    clean_html: bool = False
    metadata: dict = Field(default_factory=dict)


class ExtractResultModel(BaseModel):
    url: str
    ok: bool
    html: str
    screenshot: str | None = None   # hex-encoded bytes
    duration_ms: int
    error: str | None = None
    request: ExtractReqModel
