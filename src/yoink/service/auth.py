"""X-API-Key authentication middleware."""

from __future__ import annotations

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests missing a valid X-API-Key header.

    Authentication is skipped entirely when ``api_key`` is ``None``
    (intended for internal/trusted deployments).
    """

    _EXEMPT = {"/health"}

    def __init__(self, app, api_key: str | None) -> None:
        super().__init__(app)
        self._key = api_key

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._key is None or request.url.path in self._EXEMPT:
            return await call_next(request)

        if request.headers.get("X-API-Key") != self._key:
            return Response(
                content='{"detail":"invalid or missing X-API-Key"}',
                status_code=401,
                media_type="application/json",
            )

        return await call_next(request)
