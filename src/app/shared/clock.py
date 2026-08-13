"""Time, injectable.

``utcnow()`` is a plain convenience for tests and one-off call sites (entity
factories take ``now`` as a parameter rather than calling this themselves —
see ``User.register`` — so they stay deterministic under test). ``Clock`` is
the port a use case depends on instead of calling ``datetime.now()``
directly, so tests can freeze or advance time without patching a module
global.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utcnow()


def fixed_window_start(now: datetime, window: timedelta) -> datetime:
    """Aligns ``now`` to the start of its fixed window, anchored to the Unix
    epoch rather than to ``now`` itself — two calls landing in the same
    wall-clock window always compute the same boundary regardless of which
    one runs first. Shared by the real rate limiter adapter and its fake so
    the window-alignment math has exactly one implementation for the
    fake/real contract tests to actually be comparing (CLAUDE.md §10)."""
    elapsed_windows = (now - _EPOCH) // window
    return _EPOCH + elapsed_windows * window
