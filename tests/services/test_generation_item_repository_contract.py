"""Runs against both InMemoryGenerationItemRepository and
SqlGenerationItemRepository. The real leg seeds the full composite-FK chain
a `generation_item` sits at the bottom of: tenant, user, category, spec
version, product, product variant, a `generation_request`, a catalog image
slot and a catalog template.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.generation_item import GenerationItem
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.generation_item_repository import (
    SqlGenerationItemRepository,
)
from app.services.ports.generation_item_repository import GenerationItemRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    AssetId,
    CatalogImageSlotId,
    CatalogTemplateId,
    GenerationItemId,
    GenerationRequestId,
    TenantId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_category_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_generation_request_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.generation_item_repository import InMemoryGenerationItemRepository
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
_INSERT_SPEC_VERSION = text(
    "INSERT INTO category_spec_versions "
    "(id, tenant_id, category_id, version, status, snapshot, published_by, published_at) "
    "VALUES (:id, :tenant_id, :category_id, 1, 'published', '{}'::jsonb, :published_by, now())"
)
_INSERT_PRODUCT = text(
    "INSERT INTO products "
    "(id, tenant_id, category_id, spec_version_id, attributes, status, created_by, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :spec_version_id, '{}'::jsonb, 'draft', "
    ":created_by, now(), now())"
)
_INSERT_VARIANT = text(
    "INSERT INTO product_variants "
    "(id, tenant_id, product_id, axis_values, attributes, status, is_default, position, "
    "created_by, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :product_id, '{}'::jsonb, '{}'::jsonb, 'draft', true, 0, "
    ":created_by, now(), now())"
)
_INSERT_GENERATION_REQUEST = text(
    "INSERT INTO generation_requests "
    "(id, tenant_id, product_id, variant_id, spec_version_id, status, settings_snapshot, "
    "quota_reservation_id, requested_by, created_at) "
    "VALUES (:id, :tenant_id, :product_id, :variant_id, :spec_version_id, 'queued', '{}'::jsonb, "
    "NULL, :requested_by, now())"
)
_INSERT_CATALOG_IMAGE_SLOT = text(
    "INSERT INTO catalog_image_slots "
    "(id, tenant_id, category_id, key, label, position, aspect_ratio, target_width, "
    "target_height, is_required, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, '4:5', 1080, 1350, true, now(), now())"
)
_INSERT_CATALOG_TEMPLATE = text(
    "INSERT INTO catalog_templates "
    "(id, tenant_id, catalog_image_slot_id, name, version, is_default, position, kind, "
    "source_asset_id, status, prompt_template, prompt_version, created_by, created_at, "
    "updated_at) "
    "VALUES (:id, :tenant_id, :catalog_image_slot_id, 'Marble tabletop', 1, false, 0, "
    "'authored_scene', NULL, 'uploaded', 'A flat-lay on white marble.', 1, :created_by, "
    "now(), now())"
)


@dataclass
class Context:
    items: GenerationItemRepository
    tenant_id: TenantId
    request_id: GenerationRequestId
    catalog_image_slot_id: CatalogImageSlotId
    template_id: CatalogTemplateId
    input_asset_id: AssetId


async def _make_real_fixture() -> tuple[
    TenantId, GenerationRequestId, CatalogImageSlotId, CatalogTemplateId, AssetId
]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    request_id = new_generation_request_id()
    slot_id = new_catalog_image_slot_id()
    template_id = new_catalog_template_id()
    input_asset_id = new_asset_id()
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
        _INSERT_SPEC_VERSION,
        {
            "id": str(spec_version_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "published_by": str(user_id),
        },
    )
    await session.execute(
        _INSERT_PRODUCT,
        {
            "id": str(product_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "spec_version_id": str(spec_version_id),
            "created_by": str(user_id),
        },
    )
    await session.execute(
        _INSERT_VARIANT,
        {
            "id": str(variant_id),
            "tenant_id": str(tenant_id),
            "product_id": str(product_id),
            "created_by": str(user_id),
        },
    )
    await session.execute(
        _INSERT_GENERATION_REQUEST,
        {
            "id": str(request_id),
            "tenant_id": str(tenant_id),
            "product_id": str(product_id),
            "variant_id": str(variant_id),
            "spec_version_id": str(spec_version_id),
            "requested_by": str(user_id),
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
    await session.execute(
        _INSERT_CATALOG_TEMPLATE,
        {
            "id": str(template_id),
            "tenant_id": str(tenant_id),
            "catalog_image_slot_id": str(slot_id),
            "created_by": str(user_id),
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, request_id, slot_id, template_id, input_asset_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryGenerationItemRepository(),
            new_tenant_id(),
            new_generation_request_id(),
            new_catalog_image_slot_id(),
            new_catalog_template_id(),
            new_asset_id(),
        )
        return

    tenant_id, request_id, slot_id, template_id, input_asset_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlGenerationItemRepository(session),
            tenant_id,
            request_id,
            slot_id,
            template_id,
            input_asset_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _item(ctx: Context, **overrides: object) -> GenerationItem:
    kwargs: dict[str, object] = {
        "attempt_no": 1,
        "provider": "nano-banana",
        "model": "nano-banana-2",
        "model_params": {},
        "seed": 42,
        "prompt_rendered": "A flat-lay on white marble.",
        "prompt_version": "v1",
        "input_asset_ids": [ctx.input_asset_id],
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return GenerationItem.create(
        ctx.tenant_id, ctx.request_id, ctx.catalog_image_slot_id, ctx.template_id, **kwargs
    )


async def test_unknown_item_returns_none(ctx: Context) -> None:
    unknown_id = GenerationItemId(new_generation_item_id())
    assert await ctx.items.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    item = _item(ctx)

    await ctx.items.add(item)

    fetched = await ctx.items.get(ctx.tenant_id, item.id)
    assert fetched is not None
    assert fetched.status.value == "pending"
    assert fetched.attempt_no == 1
    assert fetched.seed == 42
    assert fetched.input_asset_ids == [ctx.input_asset_id]
    assert fetched.output_asset_id is None
    assert fetched.cost_micros is None


async def test_list_for_request_returns_every_attempt(ctx: Context) -> None:
    first = _item(ctx, attempt_no=1)
    second = _item(ctx, attempt_no=2)
    await ctx.items.add(first)
    await ctx.items.add(second)

    listed = await ctx.items.list_for_request(ctx.tenant_id, ctx.request_id)

    assert {i.id for i in listed} == {first.id, second.id}
