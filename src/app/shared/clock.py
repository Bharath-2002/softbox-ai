"""Time, injectable.

``utcnow()`` is a plain convenience for tests and one-off call sites (entity
factories take ``now`` as a parameter rather than calling this themselves —
see ``User.register`` — so they stay deterministic under test). ``Clock`` is
the port a use case depends on instead of calling ``datetime.now()``
directly, so tests can freeze or advance time without patching a module
global.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


def utcnow() -> datetime:
    return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utcnow()
