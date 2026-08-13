"""Per-tenant rate limiting at the route boundary (CLAUDE.md §9).

``rate_limit(...)`` is the reusable factory a route attaches via
``Depends(rate_limit("bucket-name", limit=..., window=...))`` — the same
shape as ``require_capability``. No route uses this yet (M1 chunk 5, see
CHECKLIST.md); it exists so the mechanism is proven ahead of the first route
that needs it.

Silently allows a request with no bound tenant (a platform-plane token)
rather than rejecting it — this dependency's only job is counting against a
tenant's limit, and a route with no tenant to key on has nothing for it to
check. Requiring a tenant at all is ``require_tenant_context``'s job, a
separate concern already enforced at router level for ``admin`` routes.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps.authorization import PrincipalDep
from app.entities.principal import Principal
from app.services.ports.rate_limiter import RateLimiter
from app.shared.clock import utcnow
from app.shared.errors import RateLimitedError


def get_rate_limiter(request: Request) -> RateLimiter:
    """Reads the instance attached to ``app.state`` — the same pattern as
    ``get_token_issuer``. Never constructs one itself: that would mean
    importing ``infrastructure``, which this layer may not do."""
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def rate_limit(
    bucket: str, *, limit: int, window: timedelta
) -> Callable[[Principal, RateLimiter], Awaitable[Principal]]:
    async def dependency(principal: PrincipalDep, limiter: RateLimiterDep) -> Principal:
        if principal.tenant_id is None:
            return principal
        allowed = await limiter.allow(
            principal.tenant_id, bucket, limit=limit, window=window, now=utcnow()
        )
        if not allowed:
            raise RateLimitedError(f"Rate limit exceeded for {bucket!r}.")
        return principal

    return dependency
