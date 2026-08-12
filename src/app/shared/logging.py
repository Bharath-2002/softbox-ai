"""Logging context — usable from any layer.

Only the *binding* of contextual identifiers lives here. Configuring the logging
pipeline (processors, renderers, redaction) is startup wiring and belongs to
``infrastructure.observability``, which only ``bootstrap`` may import.
"""

from __future__ import annotations

from typing import Any

import structlog


def get_logger(name: str | None = None) -> Any:
    """A bound logger. Typed loosely because structlog's bound type is dynamic."""
    return structlog.get_logger(name)


def bind_request_context(
    *,
    request_id: str | None = None,
    tenant_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    """Attach identifiers to every subsequent log line in this context.

    Context variables rather than parameters, so a value bound at the edge of a
    request reaches a log line deep in a use case without every function in
    between having to carry it.
    """
    values = {"request_id": request_id, "tenant_id": tenant_id, "trace_id": trace_id}
    present = {key: value for key, value in values.items() if value is not None}
    if present:
        structlog.contextvars.bind_contextvars(**present)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
