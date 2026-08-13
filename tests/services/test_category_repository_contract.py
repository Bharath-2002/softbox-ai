"""Runs against both InMemoryCategoryRepository and SqlCategoryRepository.

Same shape as ``test_audit_log_repository_contract.py`` — ``categories`` is
RLS-forced, so the real leg binds ``app.current_tenant`` on its session
before running anything. Cross-tenant behaviour through the repository (as
opposed to a fake-vs-real assertion) lives in
``tests/infrastructure/test_category_isolation.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.category import Category
from app.infrastructure.persistence.category_repository import SqlCategoryRepository
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.category_repository import CategoryRepository
from app.shared.clock import utcnow
from app.shared.ids import CategoryId, TenantId, new_category_id, new_tenant_id
from tests.fakes.category_repository import InMemoryCategoryRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    categories: CategoryRepository
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
        yield Context(InMemoryCategoryRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlCategoryRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_unknown_category_returns_none(ctx: Context) -> None:
    assert await ctx.categories.get(ctx.tenant_id, CategoryId(new_category_id())) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    category = Category.create(
        ctx.tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )

    await ctx.categories.add(category)

    fetched = await ctx.categories.get(ctx.tenant_id, category.id)
    assert fetched is not None
    assert fetched.name == "Apparel"
    assert fetched.path == category.path


async def test_list_children_returns_only_direct_children_ordered_by_position(
    ctx: Context,
) -> None:
    root = Category.create(
        ctx.tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    await ctx.categories.add(root)
    second = Category.create(
        ctx.tenant_id,
        key="bottoms",
        name="Bottoms",
        slug="bottoms",
        parent=root,
        now=utcnow(),
        position=1,
    )
    first = Category.create(
        ctx.tenant_id,
        key="tops",
        name="Tops",
        slug="tops",
        parent=root,
        now=utcnow(),
        position=0,
    )
    grandchild = Category.create(
        ctx.tenant_id, key="jackets", name="Jackets", slug="jackets", parent=first, now=utcnow()
    )
    await ctx.categories.add(second)
    await ctx.categories.add(first)
    await ctx.categories.add(grandchild)

    children = await ctx.categories.list_children(ctx.tenant_id, root.id)

    assert [c.id for c in children] == [first.id, second.id]


async def test_list_subtree_includes_self_and_every_descendant_only(ctx: Context) -> None:
    root = Category.create(
        ctx.tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    child = Category.create(
        ctx.tenant_id, key="tops", name="Tops", slug="tops", parent=root, now=utcnow()
    )
    grandchild = Category.create(
        ctx.tenant_id, key="jackets", name="Jackets", slug="jackets", parent=child, now=utcnow()
    )
    unrelated = Category.create(
        ctx.tenant_id, key="bags", name="Bags", slug="bags", parent=None, now=utcnow()
    )
    for category in (root, child, grandchild, unrelated):
        await ctx.categories.add(category)

    subtree = await ctx.categories.list_subtree(ctx.tenant_id, root.id)

    assert [c.id for c in subtree] == [root.id, child.id, grandchild.id]


async def test_update_persists_mutated_fields(ctx: Context) -> None:
    category = Category.create(
        ctx.tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    await ctx.categories.add(category)

    category.name = "Apparel & Accessories"
    await ctx.categories.update(category)

    fetched = await ctx.categories.get(ctx.tenant_id, category.id)
    assert fetched is not None
    assert fetched.name == "Apparel & Accessories"
