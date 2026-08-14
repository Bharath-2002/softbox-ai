"""Runs against both InMemoryProductInputImageRepository and
SqlProductInputImageRepository. The real leg seeds a tenant, a user, a
category, a published spec version, a product, an input image slot and an
asset, so the row's composite FKs have something real to point at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.product_input_image import ProductInputImage
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.product_input_image_repository import (
    SqlProductInputImageRepository,
)
from app.services.ports.product_input_image_repository import ProductInputImageRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    AssetId,
    InputImageSlotId,
    ProductId,
    ProductInputImageId,
    TenantId,
    UserId,
    new_asset_id,
    new_category_id,
    new_category_spec_version_id,
    new_input_image_slot_id,
    new_product_id,
    new_product_input_image_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.product_input_image_repository import InMemoryProductInputImageRepository
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
_INSERT_INPUT_IMAGE_SLOT = text(
    "INSERT INTO input_image_slots "
    "(id, tenant_id, category_id, key, label, is_required, position, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, true, 0, now(), now())"
)
_INSERT_ASSET = text(
    "INSERT INTO assets "
    "(id, tenant_id, storage_key, sha256, mime, width, height, bytes, kind, source, "
    "uploaded_by, meta, created_at) "
    "VALUES (:id, :tenant_id, :storage_key, :sha256, 'image/jpeg', 1080, 1350, 204800, "
    "'input', 'upload', :uploaded_by, '{}'::jsonb, now())"
)


@dataclass
class Context:
    images: ProductInputImageRepository
    tenant_id: TenantId
    product_id: ProductId
    input_image_slot_id: InputImageSlotId
    asset_id: AssetId
    created_by: UserId


async def _make_real_fixture() -> tuple[TenantId, ProductId, InputImageSlotId, AssetId, UserId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
    slot_id = new_input_image_slot_id()
    asset_id = new_asset_id()
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
        _INSERT_INPUT_IMAGE_SLOT,
        {
            "id": str(slot_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "key": "garment_body",
        },
    )
    await session.execute(
        _INSERT_ASSET,
        {
            "id": str(asset_id),
            "tenant_id": str(tenant_id),
            "storage_key": f"tenants/{tenant_id}/input/{asset_id}.jpg",
            "sha256": "a" * 64,
            "uploaded_by": str(user_id),
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, product_id, slot_id, asset_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryProductInputImageRepository(),
            new_tenant_id(),
            new_product_id(),
            new_input_image_slot_id(),
            new_asset_id(),
            new_user_id(),
        )
        return

    tenant_id, product_id, slot_id, asset_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlProductInputImageRepository(session),
            tenant_id,
            product_id,
            slot_id,
            asset_id,
            user_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _image(ctx: Context, **overrides: object) -> ProductInputImage:
    kwargs: dict[str, object] = {
        "input_image_slot_id": ctx.input_image_slot_id,
        "asset_id": ctx.asset_id,
        "created_by": ctx.created_by,
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return ProductInputImage.create(ctx.tenant_id, ctx.product_id, **kwargs)


async def test_unknown_image_returns_none(ctx: Context) -> None:
    unknown_id = ProductInputImageId(new_product_input_image_id())
    assert await ctx.images.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    image = _image(ctx)

    await ctx.images.add(image)

    fetched = await ctx.images.get(ctx.tenant_id, image.id)
    assert fetched is not None
    assert fetched.input_image_slot_id == ctx.input_image_slot_id
    assert fetched.asset_id == ctx.asset_id
    assert fetched.status.value == "captured"
    assert fetched.variant_id is None


async def test_list_for_product_returns_every_image(ctx: Context) -> None:
    first = _image(ctx)
    second = _image(ctx)
    await ctx.images.add(first)
    await ctx.images.add(second)

    listed = await ctx.images.list_for_product(ctx.tenant_id, ctx.product_id)

    assert {i.id for i in listed} == {first.id, second.id}


async def test_update_persists_a_rejection(ctx: Context) -> None:
    image = _image(ctx)
    await ctx.images.add(image)

    now = utcnow()
    image.start_validating(now=now)
    image.mark_rejected(reason="too blurry - retake in better light", now=now)
    await ctx.images.update(image)

    fetched = await ctx.images.get(ctx.tenant_id, image.id)
    assert fetched is not None
    assert fetched.status.value == "rejected"
    assert fetched.rejection_reason == "too blurry - retake in better light"
