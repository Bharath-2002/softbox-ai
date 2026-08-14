"""Runs against both InMemoryProductRepository and SqlProductRepository. The
real leg seeds a tenant, a user (for ``created_by``), a category and a
published ``category_spec_versions`` row, so the row's composite FKs into
``categories`` and ``category_spec_versions`` have something real to point
at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.product import Product
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.product_repository import SqlProductRepository
from app.services.ports.product_repository import ProductRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    CategoryId,
    CategorySpecVersionId,
    ProductId,
    TenantId,
    UserId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)
from app.shared.pagination import Cursor
from tests.fakes.product_repository import InMemoryProductRepository
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


@dataclass
class Context:
    products: ProductRepository
    tenant_id: TenantId
    category_id: CategoryId
    other_category_id: CategoryId
    spec_version_id: CategorySpecVersionId
    created_by: UserId


async def _make_real_fixture() -> tuple[
    TenantId, CategoryId, CategoryId, CategorySpecVersionId, UserId
]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
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
    for cid in (category_id, other_category_id):
        await session.execute(
            _INSERT_CATEGORY,
            {
                "id": str(cid),
                "tenant_id": str(tenant_id),
                "path": str(cid),
                "key": str(cid),
                "slug": str(cid),
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
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, category_id, other_category_id, spec_version_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryProductRepository(),
            new_tenant_id(),
            new_category_id(),
            new_category_id(),
            new_category_spec_version_id(),
            new_user_id(),
        )
        return

    tenant_id, category_id, other_category_id, spec_version_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlProductRepository(session),
            tenant_id,
            category_id,
            other_category_id,
            spec_version_id,
            user_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _product(
    ctx: Context, *, category_id: CategoryId | None = None, **overrides: object
) -> Product:
    kwargs: dict[str, object] = {
        "attributes": {"colour": "maroon"},
        "created_by": ctx.created_by,
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return Product.create(
        ctx.tenant_id, category_id or ctx.category_id, ctx.spec_version_id, **kwargs
    )


async def test_unknown_product_returns_none(ctx: Context) -> None:
    unknown_id = ProductId(new_product_id())
    assert await ctx.products.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    product = _product(ctx, title="Maroon silk saree", sku="SAR-001", price_amount=250_000)

    await ctx.products.add(product)

    fetched = await ctx.products.get(ctx.tenant_id, product.id)
    assert fetched is not None
    assert fetched.attributes == {"colour": "maroon"}
    assert fetched.title == "Maroon silk saree"
    assert fetched.sku == "SAR-001"
    assert fetched.price_amount == 250_000
    assert fetched.status.value == "draft"


async def test_list_for_category_returns_every_product_in_it(ctx: Context) -> None:
    first = _product(ctx)
    second = _product(ctx)
    await ctx.products.add(first)
    await ctx.products.add(second)

    listed = await ctx.products.list_for_category(ctx.tenant_id, ctx.category_id)

    assert {p.id for p in listed} == {first.id, second.id}


async def test_update_persists_attribute_changes(ctx: Context) -> None:
    product = _product(ctx)
    await ctx.products.add(product)

    product.attributes = {"colour": "teal"}
    await ctx.products.update(product)

    fetched = await ctx.products.get(ctx.tenant_id, product.id)
    assert fetched is not None
    assert fetched.attributes == {"colour": "teal"}


async def test_promoted_columns_are_nullable(ctx: Context) -> None:
    product = _product(ctx)
    await ctx.products.add(product)

    fetched = await ctx.products.get(ctx.tenant_id, product.id)
    assert fetched is not None
    assert fetched.title is None
    assert fetched.sku is None
    assert fetched.price_amount is None
    assert fetched.price_currency is None


async def test_list_page_orders_by_created_at_then_id_and_respects_limit(ctx: Context) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    first = _product(ctx, now=base)
    second = _product(ctx, now=base + timedelta(seconds=1))
    third = _product(ctx, now=base + timedelta(seconds=2))
    for product in (third, first, second):  # insertion order deliberately not chronological
        await ctx.products.add(product)

    page = await ctx.products.list_page(ctx.tenant_id, ctx.category_id, after=None, limit=2)

    assert [p.id for p in page] == [first.id, second.id]


async def test_list_page_continues_from_a_cursor_without_overlap_or_gaps(ctx: Context) -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    first = _product(ctx, now=base)
    second = _product(ctx, now=base + timedelta(seconds=1))
    third = _product(ctx, now=base + timedelta(seconds=2))
    for product in (first, second, third):
        await ctx.products.add(product)

    first_page = await ctx.products.list_page(ctx.tenant_id, ctx.category_id, after=None, limit=2)
    cursor = Cursor(sort_key=first_page[-1].created_at.isoformat(), id=first_page[-1].id)
    second_page = await ctx.products.list_page(
        ctx.tenant_id, ctx.category_id, after=cursor, limit=2
    )

    assert [p.id for p in first_page] == [first.id, second.id]
    assert [p.id for p in second_page] == [third.id]


async def test_list_page_with_no_category_filter_spans_categories(ctx: Context) -> None:
    in_category = _product(ctx)
    in_other_category = _product(ctx, category_id=ctx.other_category_id)
    await ctx.products.add(in_category)
    await ctx.products.add(in_other_category)

    page = await ctx.products.list_page(ctx.tenant_id, None, after=None, limit=10)

    assert {p.id for p in page} == {in_category.id, in_other_category.id}
