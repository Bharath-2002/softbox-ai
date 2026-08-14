"""Runs against both InMemoryOutboxEventRepository and
SqlOutboxEventRepository. ``outbox_events`` depends on nothing but
``tenants`` (see the migration's module docstring for why: an event should
outlive whatever it describes), so the real leg only needs a tenant seeded,
the same shape ``test_idempotency_repository_contract.py`` uses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.outbox_event_repository import SqlOutboxEventRepository
from app.services.ports.outbox_event_repository import OutboxEventRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.outbox_event_repository import InMemoryOutboxEventRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    events: OutboxEventRepository
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
        yield Context(InMemoryOutboxEventRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlOutboxEventRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_list_unpublished_is_empty_before_anything_is_added(ctx: Context) -> None:
    assert await ctx.events.list_unpublished(ctx.tenant_id, limit=10) == []


async def test_added_events_are_listed_as_unpublished(ctx: Context) -> None:
    await ctx.events.add(
        ctx.tenant_id, event_type="product.created", payload={"id": "abc"}, now=utcnow()
    )

    unpublished = await ctx.events.list_unpublished(ctx.tenant_id, limit=10)

    assert len(unpublished) == 1
    assert unpublished[0].event_type == "product.created"
    assert unpublished[0].payload == {"id": "abc"}
    assert unpublished[0].published_at is None


async def test_list_unpublished_is_ordered_oldest_first(ctx: Context) -> None:
    base = utcnow()
    second_id = await ctx.events.add(
        ctx.tenant_id, event_type="b", payload={}, now=base + timedelta(seconds=1)
    )
    first_id = await ctx.events.add(ctx.tenant_id, event_type="a", payload={}, now=base)

    unpublished = await ctx.events.list_unpublished(ctx.tenant_id, limit=10)

    assert [e.id for e in unpublished] == [first_id, second_id]


async def test_list_unpublished_respects_the_limit(ctx: Context) -> None:
    for i in range(3):
        await ctx.events.add(ctx.tenant_id, event_type=f"event-{i}", payload={}, now=utcnow())

    unpublished = await ctx.events.list_unpublished(ctx.tenant_id, limit=2)

    assert len(unpublished) == 2


async def test_mark_published_excludes_it_from_future_unpublished_listings(ctx: Context) -> None:
    event_id = await ctx.events.add(
        ctx.tenant_id, event_type="product.created", payload={}, now=utcnow()
    )

    await ctx.events.mark_published(ctx.tenant_id, event_id, now=utcnow())

    assert await ctx.events.list_unpublished(ctx.tenant_id, limit=10) == []
