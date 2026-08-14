"""Runs against both InMemoryProductVariantRepository and
SqlProductVariantRepository. The real leg seeds a tenant, a user, a
category, a published spec version and a product, so the row's composite FK
into ``products`` has something real to point at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.product_variant import ProductVariant
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.product_variant_repository import (
    SqlProductVariantRepository,
)
from app.services.ports.product_variant_repository import ProductVariantRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    ProductId,
    ProductVariantId,
    TenantId,
    UserId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
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


@dataclass
class Context:
    variants: ProductVariantRepository
    tenant_id: TenantId
    product_id: ProductId
    created_by: UserId


async def _make_real_fixture() -> tuple[TenantId, ProductId, UserId]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    product_id = new_product_id()
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
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, product_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryProductVariantRepository(), new_tenant_id(), new_product_id(), new_user_id()
        )
        return

    tenant_id, product_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlProductVariantRepository(session), tenant_id, product_id, user_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _variant(ctx: Context, **overrides: object) -> ProductVariant:
    kwargs: dict[str, object] = {
        "axis_values": {"colour": "maroon"},
        "created_by": ctx.created_by,
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return ProductVariant.create(ctx.tenant_id, ctx.product_id, **kwargs)


async def test_unknown_variant_returns_none(ctx: Context) -> None:
    unknown_id = ProductVariantId(new_product_variant_id())
    assert await ctx.variants.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    variant = _variant(ctx, sku="SAR-001-MAROON", attributes={"fabric": "tissue"})

    await ctx.variants.add(variant)

    fetched = await ctx.variants.get(ctx.tenant_id, variant.id)
    assert fetched is not None
    assert fetched.axis_values == {"colour": "maroon"}
    assert fetched.attributes == {"fabric": "tissue"}
    assert fetched.sku == "SAR-001-MAROON"
    assert fetched.status.value == "draft"


async def test_list_for_product_is_ordered_by_position(ctx: Context) -> None:
    first = _variant(ctx, axis_values={"colour": "maroon"})
    second = _variant(ctx, axis_values={"colour": "teal"})
    first.position = 0
    second.position = 1
    await ctx.variants.add(second)
    await ctx.variants.add(first)

    listed = await ctx.variants.list_for_product(ctx.tenant_id, ctx.product_id)

    assert [v.axis_values["colour"] for v in listed] == ["maroon", "teal"]


async def test_update_persists_attribute_changes(ctx: Context) -> None:
    variant = _variant(ctx)
    await ctx.variants.add(variant)

    variant.attributes = {"fabric": "cotton"}
    await ctx.variants.update(variant)

    fetched = await ctx.variants.get(ctx.tenant_id, variant.id)
    assert fetched is not None
    assert fetched.attributes == {"fabric": "cotton"}
