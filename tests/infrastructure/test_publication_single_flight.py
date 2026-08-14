"""``ix_publications_live_per_channel_variant`` (D21) — the backstop against
two live publications racing the same `(channel_id, variant_id)`, proven
directly against Postgres rather than through `CreatePublication` (whose
fake-backed tests cannot exercise a real index). `CreatePublication`'s
`get_live` pre-check is check-then-act; this index is what turns two
concurrent creates into one success and one loud `IntegrityError` instead
of two rows both trying to publish, mirroring
`test_category_spec_version_uniqueness.py` for D15's equivalent guard.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.entities.publication import Publication
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import (
    ProductVariantId,
    SocialAccountId,
    TenantId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_social_account_id,
    new_tenant_id,
    new_user_id,
)

pytestmark = pytest.mark.db

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
_INSERT_SOCIAL_ACCOUNT = text(
    "INSERT INTO social_accounts "
    "(id, tenant_id, provider, external_account_id, display_name, scopes, status, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, 'instagram', :external_account_id, 'Test Account', "
    "'{}', 'connected', now(), now())"
)


async def _seed(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, ProductVariantId, SocialAccountId]:
    tenant_id = new_tenant_id()
    user_id = new_user_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    channel_id = new_social_account_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
        await uow.session.execute(
            _INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )

    async with owner_uow(tenant_id) as uow:
        await uow.session.execute(
            _INSERT_CATEGORY,
            {
                "id": str(category_id),
                "tenant_id": str(tenant_id),
                "path": str(category_id),
                "key": str(category_id),
                "slug": str(category_id),
            },
        )
        await uow.session.execute(
            _INSERT_SPEC_VERSION,
            {
                "id": str(spec_version_id),
                "tenant_id": str(tenant_id),
                "category_id": str(category_id),
                "published_by": str(user_id),
            },
        )
        await uow.session.execute(
            _INSERT_PRODUCT,
            {
                "id": str(product_id),
                "tenant_id": str(tenant_id),
                "category_id": str(category_id),
                "spec_version_id": str(spec_version_id),
                "created_by": str(user_id),
            },
        )
        await uow.session.execute(
            _INSERT_VARIANT,
            {
                "id": str(variant_id),
                "tenant_id": str(tenant_id),
                "product_id": str(product_id),
                "created_by": str(user_id),
            },
        )
        await uow.session.execute(
            _INSERT_SOCIAL_ACCOUNT,
            {
                "id": str(channel_id),
                "tenant_id": str(tenant_id),
                "external_account_id": f"ig-{channel_id.hex[:8]}",
            },
        )

    return (
        tenant_id,
        ProductVariantId(variant_id),
        SocialAccountId(channel_id),
    )


async def test_two_live_publications_cannot_claim_the_same_channel_and_variant(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, variant_id, channel_id = await _seed(owner_uow)

    async with owner_uow(tenant_id) as uow:
        await uow.publications.add(
            Publication.create(
                tenant_id,
                variant_id,
                channel_id,
                content_draft_id=None,
                payload={"caption": "First.", "media_asset_ids": [], "link": None},
                now=utcnow(),
            )
        )

    with pytest.raises(IntegrityError, match="ix_publications_live_per_channel_variant"):
        async with owner_uow(tenant_id) as uow:
            await uow.publications.add(
                Publication.create(
                    tenant_id,
                    variant_id,
                    channel_id,
                    content_draft_id=None,
                    payload={"caption": "Second.", "media_asset_ids": [], "link": None},
                    now=utcnow(),
                )
            )
