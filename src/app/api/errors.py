"""Domain errors → ``application/problem+json`` (RFC 9457).

This is the only place in the codebase that knows an HTTP status code
corresponds to a domain failure. Adding a new error type means adding a row to
``_STATUS_BY_TYPE`` here, not sprinkling ``HTTPException`` through use cases.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.shared.errors import (
    AppError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitedError,
    UnavailableError,
    ValidationError,
)

PROBLEM_CONTENT_TYPE = "application/problem+json"

_STATUS_BY_TYPE: dict[type[AppError], int] = {
    ValidationError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    AuthenticationError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    QuotaExceededError: status.HTTP_402_PAYMENT_REQUIRED,
    RateLimitedError: status.HTTP_429_TOO_MANY_REQUESTS,
    UnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}

_log = structlog.get_logger(__name__)


def status_for(error: AppError) -> int:
    """Most specific match wins, so subclasses inherit their parent's status."""
    for error_type in type(error).__mro__:
        if error_type in _STATUS_BY_TYPE:
            return _STATUS_BY_TYPE[error_type]
    return status.HTTP_500_INTERNAL_SERVER_ERROR


def problem_response(
    *,
    status_code: int,
    title: str,
    code: str,
    detail: str,
    request: Request,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status_code,
        "code": code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if extra:
        body.update(extra)
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_CONTENT_TYPE)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, AppError)
        status_code = status_for(exc)
        _log.info(
            "request_failed",
            code=exc.code,
            status=status_code,
            path=request.url.path,
            details=exc.details,
        )
        return problem_response(
            status_code=status_code,
            title=exc.code.replace("_", " ").title(),
            code=exc.code,
            detail=exc.message,
            request=request,
            extra={"details": exc.details} if exc.details else None,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="Validation Error",
            code="validation_error",
            detail="The request body or parameters failed validation.",
            request=request,
            extra={"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the traceback, return nothing about it — internal detail is not
        # the caller's business and is a reliable source of information leaks.
        _log.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
        return problem_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Internal Server Error",
            code="internal_error",
            detail="An unexpected error occurred.",
            request=request,
        )
