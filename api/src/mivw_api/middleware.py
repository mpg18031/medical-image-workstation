"""ASGI middleware.

Ordering matters and is fixed in `main.create_app`: request ID, security
headers, CORS, rate limit, body size.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = structlog.get_logger(__name__)

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a correlation id and binds it to the logging context.

    The id also becomes the OpenTelemetry trace id, so a frame rendered in C++
    can be traced back to the click that caused it.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.state.request_id = request_id

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")

        response.headers["X-Request-Id"] = request_id
        log.info(
            "http.request",
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        headers = MutableHeaders(scope=response.__dict__.get("raw_headers") and None)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("Cache-Control", "no-store")

        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )

        del headers
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects oversized JSON bodies.

    Bulk data never traverses the gateway - uploads go straight to the object
    store via presigned PUT - so a large body here is either a mistake or an
    attack.
    """

    def __init__(self, app: object, max_bytes: int = 1_048_576) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            return _problem(
                request,
                413,
                "payload-too-large",
                "Request body too large",
                f"Body exceeds {self.max_bytes} bytes",
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-subject token bucket.

    In-process only, which is sufficient for `local` mode and for a single
    gateway. A multi-replica `server` deployment needs a shared store; that is
    tracked as a deployment concern rather than silently degrading here.
    """

    STRICT_PREFIXES = ("/api/v1/ingest", "/api/v1/models")

    def __init__(
        self,
        app: object,
        *,
        capacity: int = 120,
        refill_per_second: float = 2.0,
        strict_capacity: int = 10,
        strict_refill_per_second: float = 0.2,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.capacity = capacity
        self.refill = refill_per_second
        self.strict_capacity = strict_capacity
        self.strict_refill = strict_refill_per_second
        self._buckets: dict[tuple[str, bool], tuple[float, float]] = defaultdict(
            lambda: (float(capacity), time.monotonic())
        )

    def _identity(self, request: Request) -> str:
        # Prefer the authenticated subject; fall back to peer address so an
        # unauthenticated flood is still bounded.
        principal = getattr(request.state, "principal", None)
        if principal is not None:
            return str(principal.user_id)
        auth = request.headers.get("authorization", "")
        if auth:
            return f"token:{hash(auth) & 0xFFFFFFFF}"
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        strict = request.url.path.startswith(self.STRICT_PREFIXES)
        capacity = self.strict_capacity if strict else self.capacity
        refill = self.strict_refill if strict else self.refill

        key = (self._identity(request), strict)
        tokens, last_seen = self._buckets[key]

        now = time.monotonic()
        tokens = min(capacity, tokens + (now - last_seen) * refill)

        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            retry_after = max(1, int((1.0 - tokens) / refill))
            response = _problem(
                request,
                429,
                "rate-limited",
                "Too many requests",
                None,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response

        self._buckets[key] = (tokens - 1.0, now)
        return await call_next(request)


def _problem(
    request: Request,
    status: int,
    slug: str,
    title: str,
    detail: str | None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": f"https://mivw.local/problems/{slug}",
        "title": title,
        "status": status,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["requestId"] = request_id

    return JSONResponse(status_code=status, content=body, media_type="application/problem+json")
