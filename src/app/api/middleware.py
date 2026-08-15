"""Request-scoped context, plus the storefront's cache-header pass.

Assigns a request id, binds it to the logging context so every line emitted
while handling the request carries it, and echoes it back so a user reporting a
failure can quote a value that finds the logs.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.shared.logging import bind_request_context, clear_request_context

REQUEST_ID_HEADER = "X-Request-ID"

_log = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id and emit one access log line per request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Honour an inbound id so a request can be traced across services, but
        # never trust its shape — it ends up in logs.
        inbound = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if _is_safe_request_id(inbound) else uuid.uuid4().hex

        request.state.request_id = request_id
        clear_request_context()
        bind_request_context(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # The exception handlers build the response; this only records timing
            # so a failed request is not missing from the access log.
            _log.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        finally:
            clear_request_context()

        response.headers[REQUEST_ID_HEADER] = request_id
        _log.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return response


def _is_safe_request_id(value: str) -> bool:
    return bool(value) and len(value) <= 64 and value.replace("-", "").isalnum()


_PUBLIC_MAX_AGE_SECONDS = 60


class PublicCacheHeadersMiddleware(BaseHTTPMiddleware):
    """M8's Gate: "cache headers do not allow a tenant-specific response to
    be served to another tenant." A storefront response's tenant comes from
    the Host header (D4), not from the URL path — two different tenant
    domains request the identical path (``/api/v1/public/products``) and
    must never collide in a shared cache. ``Vary: Host`` is the HTTP-correct
    way to tell any conforming cache — a CDN, a shared proxy, the browser
    itself — that the response depends on that header and must be keyed on
    it, not just the path.

    ``ETag`` is a hash of the actual response body, computed here rather
    than trusted from a route handler — a route cannot forget to set it,
    and it cannot be wrong relative to what was actually sent, because
    nothing sets it except this pass over the real bytes. Only applied to
    successful, unauthenticated ``GET`` responses under ``/public/`` — no
    other route needs a tenant-agnostic cache key concern, and only a
    ``200`` has a meaningful body to key on.

    ``.../images`` responses carry presigned download URLs (D17,
    ``RequestDownload``) — a credential embedded in the body, not just
    catalogue data. Those get ``Cache-Control: private``: a shared cache
    (a CDN, a proxy) must never store or hand that URL to a second client,
    even briefly, and must never keep serving it once the presigned URL's
    own short expiry has passed. Every other ``/public/`` response is
    ``public`` — plain catalogue data, safe for a shared cache to serve to
    any client that legitimately resolves the same tenant.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)

        settings = request.app.state.settings
        public_prefix = f"{settings.api_prefix}/public/"
        if request.method != "GET" or not request.url.path.startswith(public_prefix):
            return response
        if response.status_code != 200:
            return response

        # BaseHTTPMiddleware's call_next always hands back Starlette's own
        # internal _StreamingResponse wrapper regardless of what concrete
        # type the route handler returned - a private class whose
        # body_iterator the public Response stub does not declare, so this
        # is a deliberate, documented gap rather than a blind suppression.
        body_iterator = response.body_iterator  # type: ignore[attr-defined]
        chunks = [
            chunk.encode() if isinstance(chunk, str) else bytes(chunk)
            async for chunk in body_iterator
        ]
        body = b"".join(chunks)
        etag = f'"{hashlib.sha256(body).hexdigest()}"'

        cache_scope = "private" if request.url.path.endswith("/images") else "public"

        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in ("content-length", "etag", "cache-control", "vary")
        }
        headers["ETag"] = etag
        headers["Cache-Control"] = f"{cache_scope}, max-age={_PUBLIC_MAX_AGE_SECONDS}"
        headers["Vary"] = "Host"

        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)

        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
