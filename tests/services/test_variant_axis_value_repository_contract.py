"""Runs against both InMemoryVariantAxisValueRepository and
SqlVariantAxisValueRepository.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.variant_axis import VariantAxisValue
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.variant_axis_value_repository import (
    SqlVariantAxisValueRepository,
)
from app.services.ports.variant_axis_value_repository import VariantAxisValueRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    TenantId,
    VariantAxisId,
    VariantAxisValueId,
    new_category_id,
    new_tenant_id,
    new_variant_axis_id,
    new_variant_axis_value_id,
)
from tests.fakes.variant_axis_value_repository import InMemoryVariantAxisValueRepository
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
_INSERT_AXIS = text(
    "INSERT INTO variant_axes "
    "(id, tenant_id, category_id, key, label, position, affects_imagery, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, true, now(), now())"
)


@dataclass
class Context:
    values: VariantAxisValueRepository
    tenant_id: TenantId
    axis_id: VariantAxisId


async def _make_real_tenant_and_axis() -> tuple[TenantId, VariantAxisId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    axis_id = new_variant_axis_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    await session.execute(
        _INSERT_CATEGORY,
        {
            "id": str(category_id),
            "tenant_id": str(tenant_id),
            "path": str(category_id),
            "key": str(category_id),
            "slug": str(category_id),
        },
    )
    await session.execute(
        _INSERT_AXIS,
        {
            "id": str(axis_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "key": "colour",
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, axis_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryVariantAxisValueRepository(), new_tenant_id(), new_variant_axis_id())
        return

    tenant_id, axis_id = await _make_real_tenant_and_axis()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlVariantAxisValueRepository(session), tenant_id, axis_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_unknown_value_returns_none(ctx: Context) -> None:
    unknown_id = VariantAxisValueId(new_variant_axis_value_id())
    assert await ctx.values.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    value = VariantAxisValue.create(
        ctx.tenant_id,
        ctx.axis_id,
        value="maroon",
        label="Maroon",
        now=utcnow(),
        metadata={"hex": "#800000"},
    )

    await ctx.values.add(value)

    fetched = await ctx.values.get(ctx.tenant_id, value.id)
    assert fetched is not None
    assert fetched.value == "maroon"
    assert fetched.metadata == {"hex": "#800000"}


async def test_list_for_axis_returns_only_that_axis_values(ctx: Context) -> None:
    a = VariantAxisValue.create(
        ctx.tenant_id, ctx.axis_id, value="maroon", label="Maroon", now=utcnow()
    )
    b = VariantAxisValue.create(
        ctx.tenant_id, ctx.axis_id, value="navy", label="Navy", now=utcnow()
    )
    await ctx.values.add(a)
    await ctx.values.add(b)

    listed = await ctx.values.list_for_axis(ctx.tenant_id, ctx.axis_id)

    assert {v.value for v in listed} == {"maroon", "navy"}


async def test_update_persists_mutated_fields(ctx: Context) -> None:
    value = VariantAxisValue.create(
        ctx.tenant_id, ctx.axis_id, value="maroon", label="Maroon", now=utcnow()
    )
    await ctx.values.add(value)

    value.label = "Deep maroon"
    await ctx.values.update(value)

    fetched = await ctx.values.get(ctx.tenant_id, value.id)
    assert fetched is not None
    assert fetched.label == "Deep maroon"
