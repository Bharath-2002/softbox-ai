"""Runs against both InMemoryAttributeDefinitionRepository and
SqlAttributeDefinitionRepository. Same shape as
``test_category_repository_contract.py`` — ``attribute_definitions`` is
RLS-forced, so the real leg binds ``app.current_tenant`` before running
anything, and needs a real ``categories`` row for the composite FK to point
at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.infrastructure.persistence.attribute_definition_repository import (
    SqlAttributeDefinitionRepository,
)
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.attribute_definition_repository import AttributeDefinitionRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    AttributeDefinitionId,
    CategoryId,
    TenantId,
    new_attribute_definition_id,
    new_category_id,
    new_tenant_id,
)
from tests.fakes.attribute_definition_repository import InMemoryAttributeDefinitionRepository
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
    definitions: AttributeDefinitionRepository
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
    # RLS-forced, owner role: bind the tenant so WITH CHECK is satisfied.
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
            InMemoryAttributeDefinitionRepository(),
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
            SqlAttributeDefinitionRepository(session), tenant_id, category_id, other_category_id
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _definition(ctx: Context, *, key: str = "fabric", position: int = 0) -> AttributeDefinition:
    return AttributeDefinition.create(
        ctx.tenant_id,
        ctx.category_id,
        key=key,
        label=key.title(),
        data_type=AttributeDataType.TEXT,
        position=position,
        now=utcnow(),
    )


async def test_unknown_definition_returns_none(ctx: Context) -> None:
    unknown_id = AttributeDefinitionId(new_attribute_definition_id())
    assert await ctx.definitions.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    definition = _definition(ctx)

    await ctx.definitions.add(definition)

    fetched = await ctx.definitions.get(ctx.tenant_id, definition.id)
    assert fetched is not None
    assert fetched.key == "fabric"
    assert fetched.data_type == AttributeDataType.TEXT


async def test_semantic_role_round_trips(ctx: Context) -> None:
    definition = AttributeDefinition.create(
        ctx.tenant_id,
        ctx.category_id,
        key="price",
        label="Price",
        data_type=AttributeDataType.MONEY,
        semantic_role=SemanticRole.PRICE,
        now=utcnow(),
    )

    await ctx.definitions.add(definition)

    fetched = await ctx.definitions.get(ctx.tenant_id, definition.id)
    assert fetched is not None
    assert fetched.semantic_role == SemanticRole.PRICE


async def test_list_for_category_is_ordered_by_position(ctx: Context) -> None:
    second = _definition(ctx, key="b", position=1)
    first = _definition(ctx, key="a", position=0)
    await ctx.definitions.add(second)
    await ctx.definitions.add(first)

    listed = await ctx.definitions.list_for_category(ctx.tenant_id, ctx.category_id)

    assert [d.key for d in listed] == ["a", "b"]


async def test_list_for_categories_spans_several_categories(ctx: Context) -> None:
    own = _definition(ctx, key="a")
    from_other = AttributeDefinition.create(
        ctx.tenant_id,
        ctx.other_category_id,
        key="b",
        label="B",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )
    await ctx.definitions.add(own)
    await ctx.definitions.add(from_other)

    listed = await ctx.definitions.list_for_categories(
        ctx.tenant_id, [ctx.category_id, ctx.other_category_id]
    )

    assert {d.key for d in listed} == {"a", "b"}


async def test_update_persists_mutated_fields(ctx: Context) -> None:
    definition = _definition(ctx)
    await ctx.definitions.add(definition)

    definition.label = "Fabric type"
    await ctx.definitions.update(definition)

    fetched = await ctx.definitions.get(ctx.tenant_id, definition.id)
    assert fetched is not None
    assert fetched.label == "Fabric type"
