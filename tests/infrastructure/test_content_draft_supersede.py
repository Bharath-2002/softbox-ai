"""Proves the same constraint-interaction `test_catalog_image_supersede.py`
proves for `catalog_images`, against real Postgres, for `content_drafts`
(D23). The partial unique index (`UNIQUE (tenant_id, variant_id, channel,
locale) WHERE superseded_by IS NULL`) forces `UPDATE` (retire the live row)
before `INSERT` (add the replacement) within one transaction — the reverse
order is rejected immediately by the unique index, not lazily at commit,
because `fk_content_drafts_superseded_by` is `DEFERRABLE INITIALLY
DEFERRED` and only the FK's check waits for commit.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.entities.content_draft import ContentDraft
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import (
    ProductVariantId,
    TenantId,
    new_category_id,
    new_category_spec_version_id,
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


async def _seed_chain(owner_uow: UowFactory) -> tuple[TenantId, ProductVariantId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    user_id = new_user_id()

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
    return tenant_id, variant_id


def _draft(tenant_id: TenantId, variant_id: ProductVariantId) -> ContentDraft:
    return ContentDraft.create(
        tenant_id,
        variant_id,
        channel="instagram",
        locale="en",
        body="Crafted with care.",
        alt_text="A folded saree on a neutral background.",
        model="fake-text-model",
        prompt_version="v1",
        now=utcnow(),
    )


async def test_supersede_then_insert_in_one_transaction_leaves_exactly_one_live_row(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id, variant_id = await _seed_chain(owner_uow)

    async with app_uow(tenant_id) as uow:
        draft_a = _draft(tenant_id, variant_id)
        await uow.content_drafts.add(draft_a)

    async with app_uow(tenant_id) as uow:
        live_before = await uow.content_drafts.get_live(
            tenant_id, variant_id, channel="instagram", locale="en"
        )
        assert live_before is not None
        draft_b = _draft(tenant_id, variant_id)
        # Correct order: retire the live row first (UPDATE), then insert the
        # replacement (INSERT) - both statements land in this one transaction.
        live_before.mark_superseded(by=draft_b.id, now=utcnow())
        await uow.content_drafts.update(live_before)
        await uow.content_drafts.add(draft_b)

    async with app_uow(tenant_id) as uow:
        live_after = await uow.content_drafts.get_live(
            tenant_id, variant_id, channel="instagram", locale="en"
        )
        assert live_after is not None
        assert live_after.id == draft_b.id
        old = await uow.content_drafts.get(tenant_id, draft_a.id)
        assert old is not None
        assert old.superseded_by == draft_b.id


async def test_inserting_the_replacement_before_retiring_the_live_row_is_rejected(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id, variant_id = await _seed_chain(owner_uow)

    async with app_uow(tenant_id) as uow:
        draft_a = _draft(tenant_id, variant_id)
        await uow.content_drafts.add(draft_a)

    with pytest.raises(IntegrityError):
        async with app_uow(tenant_id) as uow:
            draft_b = _draft(tenant_id, variant_id)
            # Wrong order: insert the replacement while the old row is still
            # live (superseded_by IS NULL for both) - the partial unique
            # index rejects this immediately, on the INSERT's own flush,
            # not lazily at commit.
            await uow.content_drafts.add(draft_b)
