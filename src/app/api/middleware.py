"""Request-scoped context.

Assigns a request id, binds it to the logging context so every line emitted
while handling the request carries it, and echoes it back so a user reporting a
failure can quote a value that finds the logs.
"""

from __future__ import annotations

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
