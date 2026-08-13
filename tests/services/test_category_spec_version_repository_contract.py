"""Runs against both InMemoryCategorySpecVersionRepository and
SqlCategorySpecVersionRepository. The real leg seeds a tenant, a user (for
``published_by``) and a category, so the row's composite FK into
``categories`` and plain FK into ``users`` have something real to point at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.category_spec_version import CategorySpecVersion
from app.infrastructure.persistence.category_spec_version_repository import (
    SqlCategorySpecVersionRepository,
)
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.category_spec_version_repository import CategorySpecVersionRepository
from app.shared.clock import utcnow
from app.shared.ids import CategoryId, TenantId, UserId, new_category_id, new_tenant_id, new_user_id
from tests.fakes.category_spec_version_repository import InMemoryCategorySpecVersionRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
_INSERT_USER = text(
    "INSERT INTO users (id, email, email_verified, status, created_at, updated_at) "
    "VALUES (:id, :email, true, 'active', now(), now())"
)
_INSERT_CATEGORY = text(
    "INSERT INTO categories "
    "(id, tenant_id, parent_id, path, depth, key, name, slug, position, is_active, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, NULL, :path, 0, :key, :key, :slug, 0, true, now(), now())"
)


@dataclass
class Context:
    versions: CategorySpecVersionRepository
    tenant_id: TenantId
    category_id: CategoryId
    published_by: UserId


async def _make_real_fixture() -> tuple[TenantId, CategoryId, UserId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.execute(_INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"})
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
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, category_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryCategorySpecVersionRepository(),
            new_tenant_id(),
            new_category_id(),
            new_user_id(),
        )
        return

    tenant_id, category_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlCategorySpecVersionRepository(session), tenant_id, category_id, user_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_unknown_version_returns_none(ctx: Context) -> None:
    assert await ctx.versions.get(ctx.tenant_id, new_category_id()) is None
    assert await ctx.versions.get_by_version(ctx.tenant_id, ctx.category_id, 1) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    version = CategorySpecVersion.create(
        ctx.tenant_id,
        ctx.category_id,
        version=1,
        snapshot={"attribute_definitions": [{"key": "fabric"}]},
        published_by=ctx.published_by,
        now=utcnow(),
    )

    await ctx.versions.add(version)

    fetched = await ctx.versions.get(ctx.tenant_id, version.id)
    assert fetched is not None
    assert fetched.snapshot == {"attribute_definitions": [{"key": "fabric"}]}
    assert fetched.status.value == "published"


async def test_get_by_version_finds_the_matching_row(ctx: Context) -> None:
    version = CategorySpecVersion.create(
        ctx.tenant_id,
        ctx.category_id,
        version=2,
        snapshot={},
        published_by=ctx.published_by,
        now=utcnow(),
    )
    await ctx.versions.add(version)

    fetched = await ctx.versions.get_by_version(ctx.tenant_id, ctx.category_id, 2)

    assert fetched is not None
    assert fetched.id == version.id


async def test_list_for_category_is_ordered_newest_first(ctx: Context) -> None:
    first = CategorySpecVersion.create(
        ctx.tenant_id,
        ctx.category_id,
        version=1,
        snapshot={},
        published_by=ctx.published_by,
        now=utcnow(),
    )
    second = CategorySpecVersion.create(
        ctx.tenant_id,
        ctx.category_id,
        version=2,
        snapshot={},
        published_by=ctx.published_by,
        now=utcnow(),
    )
    await ctx.versions.add(first)
    await ctx.versions.add(second)

    listed = await ctx.versions.list_for_category(ctx.tenant_id, ctx.category_id)

    assert [v.version for v in listed] == [2, 1]
