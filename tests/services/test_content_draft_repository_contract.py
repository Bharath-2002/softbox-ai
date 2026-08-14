"""Runs against both InMemoryContentDraftRepository and
SqlContentDraftRepository. The real leg seeds the chain down to a real
`product_variant`: tenant, user, category, spec version, product, variant.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.content_draft import ContentDraft, ContentDraftStatus
from app.infrastructure.persistence.content_draft_repository import SqlContentDraftRepository
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.content_draft_repository import ContentDraftRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    ContentDraftId,
    ProductVariantId,
    TenantId,
    new_category_id,
    new_category_spec_version_id,
    new_content_draft_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.content_draft_repository import InMemoryContentDraftRepository
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


@dataclass
class Context:
    drafts: ContentDraftRepository
    tenant_id: TenantId
    variant_id: ProductVariantId


async def _make_real_fixture() -> tuple[TenantId, ProductVariantId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    variant_id = new_product_variant_id()
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
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, variant_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryContentDraftRepository(), new_tenant_id(), new_product_variant_id())
        return

    tenant_id, variant_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlContentDraftRepository(session), tenant_id, variant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _draft(ctx: Context, *, channel: str = "instagram", locale: str = "en") -> ContentDraft:
    return ContentDraft.create(
        ctx.tenant_id,
        ctx.variant_id,
        channel=channel,
        locale=locale,
        body="Crafted with care.",
        alt_text="A folded saree on a neutral background.",
        model="fake-text-model",
        prompt_version="v1",
        now=utcnow(),
    )


async def test_unknown_draft_returns_none(ctx: Context) -> None:
    assert await ctx.drafts.get(ctx.tenant_id, new_content_draft_id()) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    draft = _draft(ctx)

    await ctx.drafts.add(draft)

    fetched = await ctx.drafts.get(ctx.tenant_id, draft.id)
    assert fetched is not None
    # Identity, not just `.value` equality — a read that silently degraded
    # to a bare `str` (the exact `Role`-mapping bug `mapping.py`'s own
    # docstring records) would still pass a `.value == "generated"` check.
    assert fetched.status is ContentDraftStatus.GENERATED
    assert fetched.channel == "instagram"
    assert fetched.locale == "en"
    assert fetched.hashtags == []
    assert fetched.superseded_by is None


async def test_a_widened_status_value_round_trips_through_update(ctx: Context) -> None:
    """`ContentDraftStatus` widened from a single member (`GENERATED`) to
    four (`migrations/versions/e88d14230ad4_...`). This proves the mapping
    round-trips a *second* value too, not just the one every other test in
    this file happens to exercise."""
    draft = _draft(ctx)
    await ctx.drafts.add(draft)
    draft.mark_pending_approval(now=utcnow())
    draft.approve(approved_by=None, now=utcnow())
    await ctx.drafts.update(draft)

    fetched = await ctx.drafts.get(ctx.tenant_id, draft.id)
    assert fetched is not None
    assert fetched.status is ContentDraftStatus.APPROVED
    assert fetched.approved_at is not None


async def test_get_live_finds_the_row_with_no_superseded_by(ctx: Context) -> None:
    draft = _draft(ctx)
    await ctx.drafts.add(draft)

    live = await ctx.drafts.get_live(
        ctx.tenant_id, ctx.variant_id, channel="instagram", locale="en"
    )

    assert live is not None
    assert live.id == draft.id


async def test_get_live_returns_none_once_superseded(ctx: Context) -> None:
    draft = _draft(ctx)
    await ctx.drafts.add(draft)
    draft.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=utcnow())
    await ctx.drafts.update(draft)

    live = await ctx.drafts.get_live(
        ctx.tenant_id, ctx.variant_id, channel="instagram", locale="en"
    )

    assert live is None


async def test_get_live_is_scoped_to_channel_and_locale(ctx: Context) -> None:
    draft = _draft(ctx, channel="instagram", locale="en")
    await ctx.drafts.add(draft)

    assert (
        await ctx.drafts.get_live(ctx.tenant_id, ctx.variant_id, channel="pinterest", locale="en")
        is None
    )
    assert (
        await ctx.drafts.get_live(ctx.tenant_id, ctx.variant_id, channel="instagram", locale="hi")
        is None
    )


async def test_list_for_variant_returns_every_row_including_superseded(ctx: Context) -> None:
    draft = _draft(ctx)
    await ctx.drafts.add(draft)
    draft.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=utcnow())
    await ctx.drafts.update(draft)

    listed = await ctx.drafts.list_for_variant(ctx.tenant_id, ctx.variant_id)

    assert [d.id for d in listed] == [draft.id]
    assert listed[0].superseded_by is not None
