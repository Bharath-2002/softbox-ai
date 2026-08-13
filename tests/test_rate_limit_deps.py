"""``rate_limit()`` (CLAUDE.md §9).

Tested by calling the dependency directly with a fake ``RateLimiter`` — the
same approach ``test_authorization_deps.py`` uses for ``require_capability``.
No route uses this yet (see CHECKLIST.md), so there is nothing to exercise
through FastAPI's DI or HTTP.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.api.deps.rate_limit import rate_limit
from app.entities.principal import Principal
from app.entities.roles import Role
from app.shared.errors import RateLimitedError
from app.shared.ids import TenantId, new_tenant_id, new_user_id
from tests.fakes.rate_limiter import InMemoryRateLimiter


def _principal(*, tenant_id: TenantId | None = None, is_platform_admin: bool = False) -> Principal:
    return Principal(
        user_id=new_user_id(),
        tenant_id=tenant_id,
        role=Role.VIEWER if tenant_id else None,
        is_platform_admin=is_platform_admin,
    )


async def test_allows_a_call_within_the_limit() -> None:
    principal = _principal(tenant_id=new_tenant_id())
    dependency = rate_limit("test-bucket-1", limit=2, window=timedelta(seconds=60))
    limiter = InMemoryRateLimiter()

    result = await dependency(principal, limiter)

    assert result is principal


async def test_rejects_a_call_beyond_the_limit() -> None:
    principal = _principal(tenant_id=new_tenant_id())
    dependency = rate_limit("test-bucket-2", limit=1, window=timedelta(seconds=60))
    limiter = InMemoryRateLimiter()

    await dependency(principal, limiter)

    with pytest.raises(RateLimitedError, match="test-bucket-2"):
        await dependency(principal, limiter)


async def test_a_platform_only_principal_with_no_tenant_is_not_checked() -> None:
    """Nothing to key the limit on - see the module docstring. limit=0 would
    reject every call if the check ran at all."""
    principal = _principal(is_platform_admin=True)
    dependency = rate_limit("test-bucket-3", limit=0, window=timedelta(seconds=60))
    limiter = InMemoryRateLimiter()

    result = await dependency(principal, limiter)

    assert result is principal


async def test_two_tenants_do_not_share_a_limit() -> None:
    dependency = rate_limit("test-bucket-4", limit=1, window=timedelta(seconds=60))
    limiter = InMemoryRateLimiter()
    tenant_a_principal = _principal(tenant_id=new_tenant_id())
    tenant_b_principal = _principal(tenant_id=new_tenant_id())

    await dependency(tenant_a_principal, limiter)
    result = await dependency(tenant_b_principal, limiter)

    assert result is tenant_b_principal
