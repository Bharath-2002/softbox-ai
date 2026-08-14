"""Runs against both InMemoryCatalogImageRepository and
SqlCatalogImageRepository. The real leg seeds the full chain down to a real
`generation_item` (the row a `catalog_image` points at as its winning
attempt): tenant, user, category, spec version, product, product variant,
catalog image slot, catalog template, generation request, an asset and a
generation item.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.product_variant import ProductVariant
from app.infrastructure.persistence.catalog_image_repository import SqlCatalogImageRepository
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.catalog_image_repository import CatalogImageRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    AssetId,
    CatalogImageId,
    CatalogImageSlotId,
    GenerationItemId,
    ProductId,
    ProductVariantId,
    TenantId,
    new_asset_id,
    new_catalog_image_id,
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
from app.shared.pagination import Cursor
from tests.fakes.catalog_image_repository import InMemoryCatalogImageRepository
from tests.fakes.product_variant_repository import InMemoryProductVariantRepository
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
_INSERT_ASSET = text(
    "INSERT INTO assets "
    "(id, tenant_id, storage_key, sha256, mime, width, height, bytes, kind, source, "
    "uploaded_by, meta, created_at) "
    "VALUES (:id, :tenant_id, :storage_key, :sha256, 'image/jpeg', 1080, 1350, 204800, "
    "'generated', 'generation', :uploaded_by, '{}'::jsonb, now())"
)
_INSERT_GENERATION_ITEM = text(
    "INSERT INTO generation_items "
    "(id, tenant_id, request_id, catalog_image_slot_id, template_id, attempt_no, status, "
    "provider, model, model_params, seed, prompt_rendered, prompt_version, input_asset_ids, "
    "output_asset_id, created_at) "
    "VALUES (:id, :tenant_id, :request_id, :catalog_image_slot_id, :template_id, 1, "
    "'succeeded', 'nano-banana', 'nano-banana-2', '{}'::jsonb, 42, 'rendered', 'v1', "
    "ARRAY[]::uuid[], :output_asset_id, now())"
)


@dataclass
class Context:
    images: CatalogImageRepository
    tenant_id: TenantId
    variant_id: ProductVariantId
    catalog_image_slot_id: CatalogImageSlotId
    asset_id: AssetId
    generation_item_id: GenerationItemId
    product_id: ProductId
    second_slot_id: CatalogImageSlotId


async def _make_real_fixture() -> tuple[
    TenantId,
    ProductVariantId,
    CatalogImageSlotId,
    AssetId,
    GenerationItemId,
    ProductId,
    CatalogImageSlotId,
]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    request_id = new_generation_request_id()
    slot_id = new_catalog_image_slot_id()
    second_slot_id = new_catalog_image_slot_id()
    template_id = new_catalog_template_id()
    asset_id = new_asset_id()
    generation_item_id = new_generation_item_id()
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
        _INSERT_CATALOG_IMAGE_SLOT,
        {
            "id": str(second_slot_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "key": "full_length",
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
    await session.execute(
        _INSERT_ASSET,
        {
            "id": str(asset_id),
            "tenant_id": str(tenant_id),
            "storage_key": f"tenants/{tenant_id}/generated/{asset_id}.jpg",
            "sha256": "b" * 64,
            "uploaded_by": str(user_id),
        },
    )
    await session.execute(
        _INSERT_GENERATION_ITEM,
        {
            "id": str(generation_item_id),
            "tenant_id": str(tenant_id),
            "request_id": str(request_id),
            "catalog_image_slot_id": str(slot_id),
            "template_id": str(template_id),
            "output_asset_id": str(asset_id),
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, variant_id, slot_id, asset_id, generation_item_id, product_id, second_slot_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        product_variants = InMemoryProductVariantRepository()
        tenant_id = new_tenant_id()
        product_id = new_product_id()
        variant = ProductVariant.create(
            tenant_id, product_id, axis_values={}, created_by=new_user_id(), now=utcnow()
        )
        await product_variants.add(variant)
        yield Context(
            InMemoryCatalogImageRepository(product_variants),
            tenant_id,
            variant.id,
            new_catalog_image_slot_id(),
            new_asset_id(),
            new_generation_item_id(),
            product_id,
            new_catalog_image_slot_id(),
        )
        return

    (
        tenant_id,
        variant_id,
        slot_id,
        asset_id,
        generation_item_id,
        product_id,
        second_slot_id,
    ) = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlCatalogImageRepository(session),
            tenant_id,
            variant_id,
            slot_id,
            asset_id,
            generation_item_id,
            product_id,
            second_slot_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _image(ctx: Context) -> CatalogImage:
    return CatalogImage.create(
        ctx.tenant_id,
        ctx.variant_id,
        ctx.catalog_image_slot_id,
        ctx.asset_id,
        ctx.generation_item_id,
        now=utcnow(),
    )


def _image_at_second_slot(ctx: Context) -> CatalogImage:
    """A second, independently-live row for the same variant — a different
    slot, so it never collides with `_image(ctx)`'s row under the partial
    unique index (`UNIQUE (tenant_id, variant_id, catalog_image_slot_id)
    WHERE superseded_by IS NULL`)."""
    return CatalogImage.create(
        ctx.tenant_id,
        ctx.variant_id,
        ctx.second_slot_id,
        ctx.asset_id,
        ctx.generation_item_id,
        now=utcnow(),
    )


async def test_unknown_image_returns_none(ctx: Context) -> None:
    unknown_id = CatalogImageId(new_catalog_image_id())
    assert await ctx.images.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    image = _image(ctx)

    await ctx.images.add(image)

    fetched = await ctx.images.get(ctx.tenant_id, image.id)
    assert fetched is not None
    assert fetched.status.value == "pending_qc"
    assert fetched.superseded_by is None
    assert fetched.is_primary is False


async def test_get_live_finds_the_row_with_no_superseded_by(ctx: Context) -> None:
    image = _image(ctx)
    await ctx.images.add(image)

    live = await ctx.images.get_live(ctx.tenant_id, ctx.variant_id, ctx.catalog_image_slot_id)

    assert live is not None
    assert live.id == image.id


async def test_get_live_returns_none_once_superseded(ctx: Context) -> None:
    image = _image(ctx)
    await ctx.images.add(image)
    image.mark_superseded(by=CatalogImageId(new_catalog_image_id()), now=utcnow())
    await ctx.images.update(image)

    live = await ctx.images.get_live(ctx.tenant_id, ctx.variant_id, ctx.catalog_image_slot_id)

    assert live is None


async def test_list_for_variant_returns_every_row_including_superseded(ctx: Context) -> None:
    image = _image(ctx)
    await ctx.images.add(image)
    image.mark_superseded(by=CatalogImageId(new_catalog_image_id()), now=utcnow())
    await ctx.images.update(image)

    listed = await ctx.images.list_for_variant(ctx.tenant_id, ctx.variant_id)

    assert [i.id for i in listed] == [image.id]
    assert listed[0].superseded_by is not None


async def test_list_page_excludes_superseded_rows(ctx: Context) -> None:
    superseded = _image(ctx)
    await ctx.images.add(superseded)
    live = _image(ctx)
    # Update-before-insert, same order every regeneration transaction in
    # this codebase uses (see `entities.catalog_image`'s module docstring)
    # -- the reverse order would violate the partial unique index.
    superseded.mark_superseded(by=live.id, now=utcnow())
    await ctx.images.update(superseded)
    await ctx.images.add(live)

    page = await ctx.images.list_page(
        ctx.tenant_id, status=None, product_id=None, after=None, limit=10
    )

    assert [i.id for i in page] == [live.id]


async def test_list_page_filters_by_status(ctx: Context) -> None:
    pending = _image(ctx)
    await ctx.images.add(pending)
    approved = _image_at_second_slot(ctx)
    approved.mark_qc_passed(qc_result={}, now=utcnow())
    approved.approve(approved_by=None, now=utcnow())
    await ctx.images.add(approved)

    page = await ctx.images.list_page(
        ctx.tenant_id,
        status=CatalogImageStatus.PENDING_QC,
        product_id=None,
        after=None,
        limit=10,
    )

    assert [i.id for i in page] == [pending.id]


async def test_list_page_filters_by_product(ctx: Context) -> None:
    image = _image(ctx)
    await ctx.images.add(image)

    matching = await ctx.images.list_page(
        ctx.tenant_id, status=None, product_id=ctx.product_id, after=None, limit=10
    )
    other_product = await ctx.images.list_page(
        ctx.tenant_id, status=None, product_id=new_product_id(), after=None, limit=10
    )

    assert [i.id for i in matching] == [image.id]
    assert other_product == []


async def test_list_page_paginates_with_a_cursor(ctx: Context) -> None:
    first = _image(ctx)
    await ctx.images.add(first)
    second = _image_at_second_slot(ctx)
    await ctx.images.add(second)

    first_page = await ctx.images.list_page(
        ctx.tenant_id, status=None, product_id=None, after=None, limit=1
    )
    assert len(first_page) == 1

    cursor = Cursor(sort_key=first_page[0].created_at.isoformat(), id=first_page[0].id)
    second_page = await ctx.images.list_page(
        ctx.tenant_id, status=None, product_id=None, after=cursor, limit=1
    )

    all_ids = {i.id for i in first_page} | {i.id for i in second_page}
    assert all_ids == {first.id, second.id}
