"""Liveness and readiness.

``/health`` answers "is this process alive" and must never touch a dependency —
an orchestrator that restarts the pod because Postgres blinked turns a brief
database hiccup into an outage.

``/ready`` answers "should this instance receive traffic" and does check
dependencies. Checks are registered by ``bootstrap`` rather than imported here,
so the API layer stays free of infrastructure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

# A check returns None when healthy and raises when not.
ReadinessCheck = Callable[[], Awaitable[None]]

READINESS_CHECKS_ATTR = "readiness_checks"

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    checks: dict[str, ReadinessCheck] = getattr(request.app.state, READINESS_CHECKS_ATTR, {})
    if not checks:
        return ReadinessResponse(status="ready", checks={})

    results = await asyncio.gather(*(check() for check in checks.values()), return_exceptions=True)

    report: dict[str, str] = {}
    healthy = True
    for name, result in zip(checks, results, strict=True):
        if isinstance(result, BaseException):
            healthy = False
            # The failure type, not its message — a connection error can carry a
            # DSN, and /ready is frequently exposed.
            report[name] = f"error: {type(result).__name__}"
        else:
            report[name] = "ok"

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if healthy else "degraded", checks=report)


def register_readiness_check(app: Any, name: str, check: ReadinessCheck) -> None:
    """Called by the composition root for each dependency worth gating on."""
    existing: dict[str, ReadinessCheck] = getattr(app.state, READINESS_CHECKS_ATTR, {})
    existing[name] = check
    setattr(app.state, READINESS_CHECKS_ATTR, existing)
