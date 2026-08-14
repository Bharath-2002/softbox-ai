"""Runs against both InMemoryPublicationRepository and
SqlPublicationRepository. The real leg seeds the chain down to a real
`product_variant` (same as `content_drafts`' fixture) plus a
`social_account` row for `channel_id`'s FK target.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.publication import Publication, PublicationStatus
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.publication_repository import SqlPublicationRepository
from app.services.ports.publication_repository import PublicationRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    ProductVariantId,
    PublicationId,
    SocialAccountId,
    TenantId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_publication_id,
    new_social_account_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.publication_repository import InMemoryPublicationRepository
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


@dataclass
class Context:
    publications: PublicationRepository
    tenant_id: TenantId
    variant_id: ProductVariantId
    channel_id: SocialAccountId


async def _make_real_fixture() -> tuple[TenantId, ProductVariantId, SocialAccountId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
    channel_id = new_social_account_id()
    user_id = new_user_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, email, email_verified, status, created_at, updated_at) "
            "VALUES (:id, :email, true, 'active', now(), now())"
        ),
        {"id": str(user_id), "email": f"{user_id}@example.com"},
    )
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
        _INSERT_SOCIAL_ACCOUNT,
        {
            "id": str(channel_id),
            "tenant_id": str(tenant_id),
            "external_account_id": f"ig-{channel_id.hex[:8]}",
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, variant_id, channel_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryPublicationRepository(),
            new_tenant_id(),
            new_product_variant_id(),
            new_social_account_id(),
        )
        return

    tenant_id, variant_id, channel_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlPublicationRepository(session), tenant_id, variant_id, channel_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _publication(ctx: Context) -> Publication:
    return Publication.create(
        ctx.tenant_id,
        ctx.variant_id,
        ctx.channel_id,
        content_draft_id=None,
        payload={"caption": "Crafted with care.", "media_asset_ids": [], "link": None},
        now=utcnow(),
    )


async def test_unknown_publication_returns_none(ctx: Context) -> None:
    assert await ctx.publications.get(ctx.tenant_id, PublicationId(new_publication_id())) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    publication = _publication(ctx)

    await ctx.publications.add(publication)

    fetched = await ctx.publications.get(ctx.tenant_id, publication.id)
    assert fetched is not None
    assert fetched.status is PublicationStatus.PENDING
    assert fetched.idempotency_key == publication.idempotency_key
    assert fetched.payload == {
        "caption": "Crafted with care.",
        "media_asset_ids": [],
        "link": None,
    }


async def test_update_persists_a_status_transition(ctx: Context) -> None:
    publication = _publication(ctx)
    await ctx.publications.add(publication)
    publication.mark_publishing(now=utcnow())
    publication.mark_published(external_post_id="post-1", permalink="https://x", now=utcnow())

    await ctx.publications.update(publication)

    fetched = await ctx.publications.get(ctx.tenant_id, publication.id)
    assert fetched is not None
    assert fetched.status is PublicationStatus.PUBLISHED
    assert fetched.external_post_id == "post-1"
