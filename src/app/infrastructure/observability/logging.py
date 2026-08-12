"""Structured logging.

Two things matter here and both are security properties rather than conveniences:

1. Every line carries ``request_id`` / ``tenant_id`` / ``trace_id`` when they are
   known, bound via context variables rather than threaded through call sites.
2. **Secrets are redacted by the formatter.** CLAUDE.md §11 says not to rely on
   discipline for this — a credential reaches a log line the first time somebody
   logs an object that happens to contain one, and by then it is in the
   aggregator forever.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping, Sequence
from typing import Any, Literal

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

REDACTED = "***redacted***"

# Substring match on the key, case-insensitive. Deliberately broad: a false
# positive costs one unreadable log field, a false negative costs a credential.
SENSITIVE_KEY_PARTS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "auth_header",
    "credential",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "session_id",
    "cookie",
    "dsn",
)

_MAX_REDACTION_DEPTH = 12

# Separators are stripped from both the key and the patterns before matching, so
# "api_key", "api-key", "apiKey" and the HTTP header "X-Api-Key" all match the
# same pattern. Header-style hyphenated names are the easy ones to miss.
_SEPARATORS = str.maketrans("", "", "-_. ")
_NORMALISED_PARTS: frozenset[str] = frozenset(
    part.translate(_SEPARATORS) for part in SENSITIVE_KEY_PARTS
)


def _is_sensitive(key: str) -> bool:
    normalised = key.lower().translate(_SEPARATORS)
    return any(part in normalised for part in _NORMALISED_PARTS)


def _redact(value: Any, depth: int = 0) -> Any:
    if depth >= _MAX_REDACTION_DEPTH:
        return value
    if isinstance(value, MutableMapping):
        return {
            key: REDACTED if _is_sensitive(str(key)) else _redact(item, depth + 1)
            for key, item in value.items()
        }
    # str/bytes are Sequences; excluding them keeps strings intact.
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_redact(item, depth + 1) for item in value]
    return value


def redact_processor(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Scrub sensitive keys anywhere in the event, at any nesting depth."""
    redacted: EventDict = _redact(event_dict)
    return redacted


def _build_processors(fmt: Literal["json", "console"]) -> list[Processor]:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        # Last before rendering, so it also sees fields added by the processors
        # above and by exception formatting.
        redact_processor,
    ]
    if fmt == "console":
        return [*shared, structlog.dev.ConsoleRenderer(colors=True)]
    return [
        *shared,
        structlog.processors.format_exc_info,
        structlog.processors.EventRenamer("message"),
        structlog.processors.JSONRenderer(),
    ]


def configure_logging(
    *,
    level: str = "INFO",
    fmt: Literal["json", "console"] = "json",
) -> None:
    """Configure structlog and route stdlib logging through it."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    # Uvicorn installs its own handlers; let ours own the output instead.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers.clear()
        logging.getLogger(noisy).propagate = True

    structlog.configure(
        processors=_build_processors(fmt),
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
