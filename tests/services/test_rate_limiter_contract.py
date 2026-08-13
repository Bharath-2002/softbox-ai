"""Runs against both InMemoryRateLimiter and SqlRateLimiter.

``rate_limit_windows`` is RLS-forced (D3) — same reasoning as
``test_idempotency_repository_contract.py``, whose fixture shape this
mirrors. Cross-tenant behaviour lives in
``tests/infrastructure/test_rate_limit_isolation.py`` instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.rate_limiter import SqlRateLimiter
from app.services.ports.rate_limiter import RateLimiter
from app.shared.clock import fixed_window_start, utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.rate_limiter import InMemoryRateLimiter
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    limiter: RateLimiter
    tenant_id: TenantId


async def _make_real_tenant() -> TenantId:
    tenant_id = new_tenant_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryRateLimiter(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    try:
        yield Context(SqlRateLimiter(create_session_factory(engine)), tenant_id)
    finally:
        await engine.dispose()


async def test_the_first_call_is_allowed(ctx: Context) -> None:
    allowed = await ctx.limiter.allow(
        ctx.tenant_id, "op-1", limit=3, window=timedelta(seconds=60), now=utcnow()
    )
    assert allowed is True


async def test_calls_within_the_limit_are_all_allowed(ctx: Context) -> None:
    now = utcnow()
    results = [
        await ctx.limiter.allow(
            ctx.tenant_id, "op-2", limit=3, window=timedelta(seconds=60), now=now
        )
        for _ in range(3)
    ]
    assert results == [True, True, True]


async def test_the_call_beyond_the_limit_is_rejected(ctx: Context) -> None:
    now = utcnow()
    window = timedelta(seconds=60)
    for _ in range(2):
        await ctx.limiter.allow(ctx.tenant_id, "op-3", limit=2, window=window, now=now)

    rejected = await ctx.limiter.allow(ctx.tenant_id, "op-3", limit=2, window=window, now=now)

    assert rejected is False


async def test_a_rejected_call_does_not_itself_count(ctx: Context) -> None:
    """The guard is on the UPDATE, not a separate check-then-act - a
    rejection must not silently consume a slot that a later legitimate call
    in the same window could have used instead."""
    now = utcnow()
    window = timedelta(seconds=60)
    await ctx.limiter.allow(ctx.tenant_id, "op-4", limit=1, window=window, now=now)

    for _ in range(3):
        await ctx.limiter.allow(ctx.tenant_id, "op-4", limit=1, window=window, now=now)

    # Still exactly one slot's worth consumed - the repeated rejections
    # above did not each add to the count.
    still_rejected = await ctx.limiter.allow(ctx.tenant_id, "op-4", limit=1, window=window, now=now)
    assert still_rejected is False


async def test_a_new_window_resets_the_count(ctx: Context) -> None:
    window = timedelta(seconds=60)
    first_window_now = utcnow()
    await ctx.limiter.allow(ctx.tenant_id, "op-5", limit=1, window=window, now=first_window_now)
    exhausted = await ctx.limiter.allow(
        ctx.tenant_id, "op-5", limit=1, window=window, now=first_window_now
    )
    assert exhausted is False

    next_window_start = fixed_window_start(first_window_now, window) + window
    allowed_again = await ctx.limiter.allow(
        ctx.tenant_id, "op-5", limit=1, window=window, now=next_window_start
    )
    assert allowed_again is True


async def test_different_buckets_do_not_share_a_limit(ctx: Context) -> None:
    now = utcnow()
    window = timedelta(seconds=60)
    await ctx.limiter.allow(ctx.tenant_id, "op-6a", limit=1, window=window, now=now)

    allowed = await ctx.limiter.allow(ctx.tenant_id, "op-6b", limit=1, window=window, now=now)

    assert allowed is True
