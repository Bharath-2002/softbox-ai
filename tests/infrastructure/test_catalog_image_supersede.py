"""The M5 Gate's "regeneration sets `superseded_by` and inserts in one
transaction" bullet (D18). The partial unique index
(`UNIQUE (tenant_id, variant_id, catalog_image_slot_id) WHERE superseded_by
IS NULL`) is what makes ordering inside that transaction non-interchangeable:
Postgres checks a non-deferred unique index at the end of each statement,
not at commit, so the existing live row's `superseded_by` must be set
**before** the replacement is inserted. Proven both ways against real
Postgres: the correct order commits cleanly and leaves exactly one live row;
the reversed order raises a unique violation immediately on the `INSERT`,
not lazily at commit time.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.entities.catalog_image import CatalogImage
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import (
    CatalogImageSlotId,
    GenerationItemId,
    ProductVariantId,
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

pytestmark = pytest.mark.db

UowFactory = Callable[[TenantId | None], SqlUnitOfWork]

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
    "VALUES (:id, :tenant_id, :request_id, :catalog_image_slot_id, :template_id, :attempt_no, "
    "'succeeded', 'nano-banana', 'nano-banana-2', '{}'::jsonb, 42, 'rendered', 'v1', "
    "ARRAY[]::uuid[], :output_asset_id, now())"
)


async def _seed_chain(
    owner_uow: UowFactory,
) -> tuple[TenantId, ProductVariantId, CatalogImageSlotId, GenerationItemId, GenerationItemId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    request_id = new_generation_request_id()
    slot_id = new_catalog_image_slot_id()
    template_id = new_catalog_template_id()
    user_id = new_user_id()
    asset_a_id = new_asset_id()
    asset_b_id = new_asset_id()
    item_a_id = new_generation_item_id()
    item_b_id = new_generation_item_id()

    async with owner_uow(tenant_id) as uow:
        session = uow.session
        await session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
        await session.execute(_INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"})
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
        for asset_id, sha in ((asset_a_id, "c" * 64), (asset_b_id, "d" * 64)):
            await session.execute(
                _INSERT_ASSET,
                {
                    "id": str(asset_id),
                    "tenant_id": str(tenant_id),
                    "storage_key": f"tenants/{tenant_id}/generated/{asset_id}.jpg",
                    "sha256": sha,
                    "uploaded_by": str(user_id),
                },
            )
        await session.execute(
            _INSERT_GENERATION_ITEM,
            {
                "id": str(item_a_id),
                "tenant_id": str(tenant_id),
                "request_id": str(request_id),
                "catalog_image_slot_id": str(slot_id),
                "template_id": str(template_id),
                "attempt_no": 1,
                "output_asset_id": str(asset_a_id),
            },
        )
        await session.execute(
            _INSERT_GENERATION_ITEM,
            {
                "id": str(item_b_id),
                "tenant_id": str(tenant_id),
                "request_id": str(request_id),
                "catalog_image_slot_id": str(slot_id),
                "template_id": str(template_id),
                "attempt_no": 2,
                "output_asset_id": str(asset_b_id),
            },
        )
    return tenant_id, variant_id, slot_id, item_a_id, item_b_id


async def test_supersede_then_insert_in_one_transaction_leaves_exactly_one_live_row(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id, variant_id, slot_id, item_a_id, item_b_id = await _seed_chain(owner_uow)

    async with owner_uow(tenant_id) as uow:
        asset_a = (
            await uow.session.execute(
                text("SELECT output_asset_id FROM generation_items WHERE id = :id"),
                {"id": str(item_a_id)},
            )
        ).scalar_one()
        asset_b = (
            await uow.session.execute(
                text("SELECT output_asset_id FROM generation_items WHERE id = :id"),
                {"id": str(item_b_id)},
            )
        ).scalar_one()

    async with app_uow(tenant_id) as uow:
        image_a = CatalogImage.create(
            tenant_id, variant_id, slot_id, asset_a, item_a_id, now=utcnow()
        )
        await uow.catalog_images.add(image_a)

    async with app_uow(tenant_id) as uow:
        live_before = await uow.catalog_images.get_live(tenant_id, variant_id, slot_id)
        assert live_before is not None
        image_b = CatalogImage.create(
            tenant_id, variant_id, slot_id, asset_b, item_b_id, now=utcnow()
        )
        # Correct order: retire the live row first (UPDATE), then insert the
        # replacement (INSERT) - both statements land in this one transaction.
        live_before.mark_superseded(by=image_b.id, now=utcnow())
        await uow.catalog_images.update(live_before)
        await uow.catalog_images.add(image_b)

    async with app_uow(tenant_id) as uow:
        live_after = await uow.catalog_images.get_live(tenant_id, variant_id, slot_id)
        assert live_after is not None
        assert live_after.id == image_b.id
        old = await uow.catalog_images.get(tenant_id, image_a.id)
        assert old is not None
        assert old.superseded_by == image_b.id


async def test_inserting_the_replacement_before_retiring_the_live_row_is_rejected(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id, variant_id, slot_id, item_a_id, item_b_id = await _seed_chain(owner_uow)

    async with owner_uow(tenant_id) as uow:
        asset_a = (
            await uow.session.execute(
                text("SELECT output_asset_id FROM generation_items WHERE id = :id"),
                {"id": str(item_a_id)},
            )
        ).scalar_one()
        asset_b = (
            await uow.session.execute(
                text("SELECT output_asset_id FROM generation_items WHERE id = :id"),
                {"id": str(item_b_id)},
            )
        ).scalar_one()

    async with app_uow(tenant_id) as uow:
        image_a = CatalogImage.create(
            tenant_id, variant_id, slot_id, asset_a, item_a_id, now=utcnow()
        )
        await uow.catalog_images.add(image_a)

    with pytest.raises(IntegrityError):
        async with app_uow(tenant_id) as uow:
            image_b = CatalogImage.create(
                tenant_id, variant_id, slot_id, asset_b, item_b_id, now=utcnow()
            )
            # Wrong order: insert the replacement while the old row is still
            # live (superseded_by IS NULL for both) - the partial unique
            # index rejects this immediately, on the INSERT's own flush,
            # not lazily at commit.
            await uow.catalog_images.add(image_b)
