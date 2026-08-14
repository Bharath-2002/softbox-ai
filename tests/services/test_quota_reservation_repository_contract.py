"""Runs against both InMemoryQuotaReservationRepository and
SqlQuotaReservationRepository. ``quota_reservations`` depends on nothing
but ``tenants``, same shape as ``test_task_queue_contract.py``.

The concurrency property this port exists for — N parallel `reserve()`
calls against a budget of M < N reserve exactly M — cannot be expressed
with this file's single-session-per-context fixture; that lives in
``tests/infrastructure/test_quota_reservation_concurrency.py`` instead,
against real Postgres only, using genuinely separate connections (the same
shape ``test_task_queue_concurrency.py`` already proved out).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.quota_reservation_repository import (
    SqlQuotaReservationRepository,
)
from app.services.ports.quota_reservation_repository import QuotaReservationRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.quota_reservation_repository import InMemoryQuotaReservationRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    quota: QuotaReservationRepository
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
        yield Context(InMemoryQuotaReservationRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlQuotaReservationRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_reserve_against_an_unprovisioned_metric_fails_closed(ctx: Context) -> None:
    reserved = await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=1, now=utcnow()
    )

    assert reserved is False


async def test_ensure_period_then_reserve_within_limit_succeeds(ctx: Context) -> None:
    now = utcnow()
    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=10, now=now
    )

    reserved = await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=3, now=now
    )

    assert reserved is True
    row = await ctx.quota.get(ctx.tenant_id, period="2026-08", metric="generation.images")
    assert row is not None
    assert row.reserved == 3
    assert row.limit_value == 10


async def test_reserve_beyond_the_limit_fails(ctx: Context) -> None:
    now = utcnow()
    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=5, now=now
    )
    await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=5, now=now
    )

    reserved = await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=1, now=now
    )

    assert reserved is False


async def test_ensure_period_does_not_overwrite_an_existing_limit(ctx: Context) -> None:
    now = utcnow()
    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=10, now=now
    )

    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=999, now=now
    )

    row = await ctx.quota.get(ctx.tenant_id, period="2026-08", metric="generation.images")
    assert row is not None
    assert row.limit_value == 10


async def test_commit_increases_the_reporting_counter_without_touching_reserved(
    ctx: Context,
) -> None:
    now = utcnow()
    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=10, now=now
    )
    await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=4, now=now
    )

    await ctx.quota.commit(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=4, now=now
    )

    row = await ctx.quota.get(ctx.tenant_id, period="2026-08", metric="generation.images")
    assert row is not None
    assert row.reserved == 4
    assert row.committed == 4


async def test_release_gives_the_quantity_back_to_reserved(ctx: Context) -> None:
    now = utcnow()
    await ctx.quota.ensure_period(
        ctx.tenant_id, period="2026-08", metric="generation.images", limit_value=10, now=now
    )
    await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=4, now=now
    )

    await ctx.quota.release(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=4, now=now
    )

    row = await ctx.quota.get(ctx.tenant_id, period="2026-08", metric="generation.images")
    assert row is not None
    assert row.reserved == 0
    assert row.committed == 0

    # The released quota is usable again.
    reserved_again = await ctx.quota.reserve(
        ctx.tenant_id, period="2026-08", metric="generation.images", quantity=10, now=now
    )
    assert reserved_again is True


async def test_get_on_an_unprovisioned_metric_returns_none(ctx: Context) -> None:
    assert await ctx.quota.get(ctx.tenant_id, period="2026-08", metric="unknown") is None
