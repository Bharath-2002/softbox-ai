"""Runs against both InMemoryCatalogTemplateRepository and
SqlCatalogTemplateRepository. The real leg seeds a tenant, a user (for
``created_by``), a category and a catalog image slot, so the row's
composite FK into ``catalog_image_slots`` and plain FK into ``users`` have
something real to point at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.catalog_template import CatalogTemplate
from app.infrastructure.persistence.catalog_template_repository import (
    SqlCatalogTemplateRepository,
)
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.catalog_template_repository import CatalogTemplateRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    CatalogImageSlotId,
    CatalogTemplateId,
    TenantId,
    UserId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_category_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.catalog_template_repository import InMemoryCatalogTemplateRepository
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
_INSERT_CATALOG_IMAGE_SLOT = text(
    "INSERT INTO catalog_image_slots "
    "(id, tenant_id, category_id, key, label, position, aspect_ratio, target_width, "
    "target_height, is_required, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, '4:5', 1080, 1350, true, now(), now())"
)


@dataclass
class Context:
    templates: CatalogTemplateRepository
    tenant_id: TenantId
    catalog_image_slot_id: CatalogImageSlotId
    created_by: UserId


async def _make_real_fixture() -> tuple[TenantId, CatalogImageSlotId, UserId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    slot_id = new_catalog_image_slot_id()
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
    await session.execute(
        _INSERT_CATALOG_IMAGE_SLOT,
        {
            "id": str(slot_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "key": "closeup",
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, slot_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryCatalogTemplateRepository(),
            new_tenant_id(),
            new_catalog_image_slot_id(),
            new_user_id(),
        )
        return

    tenant_id, slot_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlCatalogTemplateRepository(session), tenant_id, slot_id, user_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _authored(ctx: Context, *, name: str = "Marble tabletop", version: int = 1) -> CatalogTemplate:
    return CatalogTemplate.create_authored(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        name=name,
        prompt_template="A flat-lay on white marble, soft daylight.",
        created_by=ctx.created_by,
        now=utcnow(),
        version=version,
    )


async def test_unknown_template_returns_none(ctx: Context) -> None:
    unknown_id = CatalogTemplateId(new_catalog_template_id())
    assert await ctx.templates.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    template = _authored(ctx)

    await ctx.templates.add(template)

    fetched = await ctx.templates.get(ctx.tenant_id, template.id)
    assert fetched is not None
    assert fetched.name == "Marble tabletop"
    assert fetched.prompt_template == template.prompt_template


async def test_list_for_catalog_slot_is_ordered_by_position(ctx: Context) -> None:
    first = _authored(ctx, name="a")
    second = _authored(ctx, name="b")
    first.position = 0
    second.position = 1
    await ctx.templates.add(second)
    await ctx.templates.add(first)

    listed = await ctx.templates.list_for_catalog_slot(ctx.tenant_id, ctx.catalog_image_slot_id)

    assert [t.name for t in listed] == ["a", "b"]


async def test_get_latest_version_returns_the_highest_version(ctx: Context) -> None:
    v1 = _authored(ctx, name="Marble tabletop", version=1)
    v2 = _authored(ctx, name="Marble tabletop", version=2)
    await ctx.templates.add(v1)
    await ctx.templates.add(v2)

    latest = await ctx.templates.get_latest_version(
        ctx.tenant_id, ctx.catalog_image_slot_id, "Marble tabletop"
    )

    assert latest is not None
    assert latest.version == 2


async def test_get_latest_version_returns_none_for_an_unknown_name(ctx: Context) -> None:
    latest = await ctx.templates.get_latest_version(
        ctx.tenant_id, ctx.catalog_image_slot_id, "Nonexistent"
    )

    assert latest is None


async def test_update_persists_a_state_transition(ctx: Context) -> None:
    template = _authored(ctx)
    await ctx.templates.add(template)

    now = utcnow()
    template.start_analysing(now=now)
    template.mark_analysed(
        prompt_template=template.prompt_template or "",
        analysis=None,
        analysis_model=None,
        now=now,
    )
    await ctx.templates.update(template)

    fetched = await ctx.templates.get(ctx.tenant_id, template.id)
    assert fetched is not None
    assert fetched.status.value == "analysed"


async def test_source_asset_id_is_nullable_for_authored_templates(ctx: Context) -> None:
    template = _authored(ctx)
    await ctx.templates.add(template)

    fetched = await ctx.templates.get(ctx.tenant_id, template.id)
    assert fetched is not None
    assert fetched.source_asset_id is None


async def test_a_bare_source_asset_id_is_accepted_by_the_fake_but_would_need_a_real_row() -> None:
    # Documents the composite-FK boundary rather than exercising it: the SQL
    # leg needs a real `assets` row to satisfy `fk_catalog_templates_source_asset`,
    # which is exactly what the upload flow (test_admin_assets_upload_flow.py)
    # already proves creates a real, tenant-scoped asset row before anything
    # references it. This test only pins the fake's shape.
    fake = InMemoryCatalogTemplateRepository()
    tenant_id = new_tenant_id()
    template = CatalogTemplate.create_from_upload(
        tenant_id,
        new_catalog_image_slot_id(),
        name="Studio flatlay",
        source_asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=utcnow(),
    )

    await fake.add(template)

    fetched = await fake.get(tenant_id, template.id)
    assert fetched is not None
    assert fetched.source_asset_id is not None
