"""Proves `CompleteGenerationItemRender` itself — not a hand-driven
`CatalogImage.create`/`mark_superseded`/`update`/`add` sequence — emits the
same update-before-insert order `test_catalog_image_supersede.py` proves
against the partial unique index and the deferrable FK. That file proves
the *ordering* is correct; this one proves the *use case* actually produces
it, against real Postgres, given `catalog_images`' FK ordering already bit
this exact area once (see `entities.catalog_image`'s module docstring).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from PIL import Image
from sqlalchemy import text

from app.features.generation.complete_generation_item_render import CompleteGenerationItemRender
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.ids import (
    CatalogImageSlotId,
    GenerationItemId,
    ProductVariantId,
    TenantId,
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
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage

pytestmark = pytest.mark.db

UowFactory = Callable[[TenantId | None], SqlUnitOfWork]
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _png_bytes(*, color: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color=color).save(buf, format="PNG")
    return buf.getvalue()


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
_INSERT_RUNNING_GENERATION_ITEM = text(
    "INSERT INTO generation_items "
    "(id, tenant_id, request_id, catalog_image_slot_id, template_id, attempt_no, status, "
    "provider, model, model_params, seed, prompt_rendered, prompt_version, input_asset_ids, "
    "created_at) "
    "VALUES (:id, :tenant_id, :request_id, :catalog_image_slot_id, :template_id, :attempt_no, "
    "'running', 'nano-banana', 'nano-banana-2', '{}'::jsonb, 42, 'rendered', 'v1', "
    "ARRAY[]::uuid[], now())"
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
        for item_id, attempt_no in ((item_a_id, 1), (item_b_id, 2)):
            await session.execute(
                _INSERT_RUNNING_GENERATION_ITEM,
                {
                    "id": str(item_id),
                    "tenant_id": str(tenant_id),
                    "request_id": str(request_id),
                    "catalog_image_slot_id": str(slot_id),
                    "template_id": str(template_id),
                    "attempt_no": attempt_no,
                },
            )
    return tenant_id, variant_id, slot_id, item_a_id, item_b_id


async def test_completing_two_items_for_the_same_slot_leaves_exactly_one_live_catalog_image(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id, variant_id, slot_id, item_a_id, item_b_id = await _seed_chain(owner_uow)
    storage = InMemoryObjectStorage()
    use_case = CompleteGenerationItemRender(app_uow, storage, FakeClock(_NOW))

    async with app_uow(tenant_id) as uow:
        job_a_id = await uow.task_queue.enqueue(
            tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW
        )
        job_b_id = await uow.task_queue.enqueue(
            tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW
        )

    item_a = await use_case(
        tenant_id=tenant_id,
        item_id=item_a_id,
        job_id=job_a_id,
        image_bytes=_png_bytes(color="red"),
        cost_micros=1_000,
        latency_ms=250,
    )

    async with app_uow(tenant_id) as uow:
        live_before = await uow.catalog_images.get_live(tenant_id, variant_id, slot_id)
    assert live_before is not None
    assert live_before.generation_item_id == item_a.id

    item_b = await use_case(
        tenant_id=tenant_id,
        item_id=item_b_id,
        job_id=job_b_id,
        image_bytes=_png_bytes(color="blue"),
        cost_micros=1_000,
        latency_ms=250,
    )

    async with app_uow(tenant_id) as uow:
        live_after = await uow.catalog_images.get_live(tenant_id, variant_id, slot_id)
        assert live_after is not None
        assert live_after.generation_item_id == item_b.id
        all_images = await uow.catalog_images.list_for_variant(tenant_id, variant_id)
    assert len(all_images) == 2
    old = next(i for i in all_images if i.id != live_after.id)
    assert old.superseded_by == live_after.id
