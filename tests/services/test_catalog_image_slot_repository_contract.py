"""Runs against both InMemoryCatalogImageSlotRepository and
SqlCatalogImageSlotRepository. Same shape as
``test_input_image_slot_repository_contract.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.image_slots import CatalogImageSlot
from app.infrastructure.persistence.catalog_image_slot_repository import (
    SqlCatalogImageSlotRepository,
)
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.catalog_image_slot_repository import CatalogImageSlotRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    CatalogImageSlotId,
    CategoryId,
    TenantId,
    new_catalog_image_slot_id,
    new_category_id,
    new_tenant_id,
)
from tests.fakes.catalog_image_slot_repository import InMemoryCatalogImageSlotRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
_INSERT_CATEGORY = text(
    "INSERT INTO categories "
    "(id, tenant_id, parent_id, path, depth, key, name, slug, position, is_active, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, NULL, :path, 0, :key, :key, :slug, 0, true, now(), now())"
)


@dataclass
class Context:
    slots: CatalogImageSlotRepository
    tenant_id: TenantId
    category_id: CategoryId
    other_category_id: CategoryId


async def _make_real_tenant_and_categories() -> tuple[TenantId, CategoryId, CategoryId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    for cid in (category_id, other_category_id):
        await session.execute(
            _INSERT_CATEGORY,
            {
                "id": str(cid),
                "tenant_id": str(tenant_id),
                "path": str(cid),
                "key": str(cid),
                "slug": str(cid),
            },
        )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, category_id, other_category_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryCatalogImageSlotRepository(),
            new_tenant_id(),
            new_category_id(),
            new_category_id(),
        )
        return

    tenant_id, category_id, other_category_id = await _make_real_tenant_and_categories()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlCatalogImageSlotRepository(session), tenant_id, category_id, other_category_id
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _slot(ctx: Context, *, key: str = "closeup", position: int = 0) -> CatalogImageSlot:
    return CatalogImageSlot.create(
        ctx.tenant_id,
        ctx.category_id,
        key=key,
        label=key.title(),
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        position=position,
        now=utcnow(),
    )


async def test_unknown_slot_returns_none(ctx: Context) -> None:
    unknown_id = CatalogImageSlotId(new_catalog_image_slot_id())
    assert await ctx.slots.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    slot = _slot(ctx)

    await ctx.slots.add(slot)

    fetched = await ctx.slots.get(ctx.tenant_id, slot.id)
    assert fetched is not None
    assert fetched.aspect_ratio == "4:5"
    assert fetched.target_width == 1080


async def test_list_for_category_is_ordered_by_position(ctx: Context) -> None:
    second = _slot(ctx, key="b", position=1)
    first = _slot(ctx, key="a", position=0)
    await ctx.slots.add(second)
    await ctx.slots.add(first)

    listed = await ctx.slots.list_for_category(ctx.tenant_id, ctx.category_id)

    assert [s.key for s in listed] == ["a", "b"]


async def test_list_for_categories_spans_several_categories(ctx: Context) -> None:
    own = _slot(ctx, key="a")
    from_other = CatalogImageSlot.create(
        ctx.tenant_id,
        ctx.other_category_id,
        key="b",
        label="B",
        aspect_ratio="1:1",
        target_width=1080,
        target_height=1080,
        now=utcnow(),
    )
    await ctx.slots.add(own)
    await ctx.slots.add(from_other)

    listed = await ctx.slots.list_for_categories(
        ctx.tenant_id, [ctx.category_id, ctx.other_category_id]
    )

    assert {s.key for s in listed} == {"a", "b"}


async def test_update_persists_mutated_fields(ctx: Context) -> None:
    slot = _slot(ctx)
    await ctx.slots.add(slot)

    slot.label = "Close-up (revised)"
    await ctx.slots.update(slot)

    fetched = await ctx.slots.get(ctx.tenant_id, slot.id)
    assert fetched is not None
    assert fetched.label == "Close-up (revised)"
