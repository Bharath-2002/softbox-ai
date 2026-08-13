"""Per-tenant rate limiting (CLAUDE.md §9), Postgres-backed per D19 (no
Redis in v1).

Fixed window, not sliding or token-bucket — the same conditional-UPDATE
atomic-reservation shape D24's quota reservation already uses (a
``count < limit`` guard on the update, not a separate check-then-act), so
this adds no new mechanism to the codebase, just a second table shaped to
fit it.

Per-*tenant* only, deliberately. Per-IP is out of scope: ``request.client.host``
behind a load balancer or reverse proxy is the proxy's address, not the
caller's, and trusting ``X-Forwarded-For`` requires knowing how many hops to
strip — a decision that depends on the eventual deployment topology, which
is not chosen yet. A limiter keyed on a value already known to be wrong
would be worse than no limiter (see CHECKLIST.md for the explicit
deferral), so this port has no IP concept at all rather than a half-built
one.

Not a ``UnitOfWork`` property, unlike ``IdempotencyRepository``: a rate
check runs *before* a use case's own transaction opens and its outcome does
not need to commit atomically with anything downstream — a window's counter
is meaningful on its own and simply expires on the next tick regardless of
what the guarded request goes on to do. Constructed once in ``bootstrap``
and reached the same way ``TokenIssuer`` is — attached to ``app.state``, read
through a small dependency in ``api/deps/``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.shared.ids import TenantId


class RateLimiter(Protocol):
    async def allow(
        self, tenant_id: TenantId, bucket: str, *, limit: int, window: timedelta, now: datetime
    ) -> bool:
        """Atomically counts this call against ``bucket``'s current fixed
        window and reports whether it was under ``limit``. A call that
        returns ``False`` was rejected, not silently dropped — Postgres
        never performs the underlying update when the ``count < limit``
        guard fails, so a rejected call does not itself count toward a
        later successful one in the same window."""
        ...
