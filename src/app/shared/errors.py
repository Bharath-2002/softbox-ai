"""Domain error hierarchy.

These carry a stable machine-readable ``code`` and nothing about HTTP. The
mapping from error type to status code lives in ``app.api`` — the domain must
stay usable from a worker, a CLI, or a test with no web framework in sight.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for every error the application raises deliberately."""

    code = "error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details: dict[str, Any] = details or {}

    def __str__(self) -> str:
        return self.message


class ValidationError(AppError):
    """Input violated a domain rule."""

    code = "validation_error"


class NotFoundError(AppError):
    """The requested resource does not exist, or is not visible to this tenant.

    Deliberately does not distinguish those two cases: telling a caller that a
    resource exists but belongs to someone else is itself a leak.
    """

    code = "not_found"


class ConflictError(AppError):
    """The request contradicts current state — duplicate key, lost update."""

    code = "conflict"


class AuthenticationError(AppError):
    """No valid credentials were presented."""

    code = "unauthenticated"


class PermissionDeniedError(AppError):
    """Authenticated, but lacking the required capability."""

    code = "permission_denied"


class QuotaExceededError(AppError):
    """The tenant's budget for a metered resource is exhausted (D24)."""

    code = "quota_exceeded"


class RateLimitedError(AppError):
    """Too many requests, or an external channel's rate limit would be breached."""

    code = "rate_limited"


class UnavailableError(AppError):
    """A dependency the operation needs is not currently usable."""

    code = "unavailable"
