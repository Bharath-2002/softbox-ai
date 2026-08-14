"""Runs against both InMemoryGenerationRequestRepository and
SqlGenerationRequestRepository. The real leg seeds a tenant, a user, a
category, a published spec version, a product and a product variant, so the
row's composite FKs have something real to point at. `quota_reservation_id`
is left `None` in these tests - the reserve-then-fetch-id sequence that
populates it belongs to `CreateGenerationRequest`, not this storage layer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.generation_request import GenerationRequest
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.generation_request_repository import (
    SqlGenerationRequestRepository,
)
from app.services.ports.generation_request_repository import GenerationRequestRepository
from app.shared.clock import utcnow
from app.shared.ids import (
    CategorySpecVersionId,
    GenerationRequestId,
    ProductId,
    ProductVariantId,
    TenantId,
    UserId,
    new_category_id,
    new_category_spec_version_id,
    new_generation_request_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.generation_request_repository import InMemoryGenerationRequestRepository
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
    requests: GenerationRequestRepository
    tenant_id: TenantId
    product_id: ProductId
    variant_id: ProductVariantId
    spec_version_id: CategorySpecVersionId
    requested_by: UserId


async def _make_real_fixture() -> tuple[
    TenantId, ProductId, ProductVariantId, CategorySpecVersionId, UserId
]:
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
    return tenant_id, product_id, variant_id, spec_version_id, user_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryGenerationRequestRepository(),
            new_tenant_id(),
            new_product_id(),
            new_product_variant_id(),
            new_category_spec_version_id(),
            new_user_id(),
        )
        return

    tenant_id, product_id, variant_id, spec_version_id, user_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlGenerationRequestRepository(session),
            tenant_id,
            product_id,
            variant_id,
            spec_version_id,
            user_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _request(ctx: Context, **overrides: object) -> GenerationRequest:
    kwargs: dict[str, object] = {
        "settings_snapshot": {},
        "quota_reservation_id": None,
        "requested_by": ctx.requested_by,
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return GenerationRequest.create(
        ctx.tenant_id, ctx.product_id, ctx.variant_id, ctx.spec_version_id, **kwargs
    )


async def test_unknown_request_returns_none(ctx: Context) -> None:
    unknown_id = GenerationRequestId(new_generation_request_id())
    assert await ctx.requests.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    request = _request(ctx)

    await ctx.requests.add(request)

    fetched = await ctx.requests.get(ctx.tenant_id, request.id)
    assert fetched is not None
    assert fetched.status.value == "queued"
    assert fetched.product_id == ctx.product_id
    assert fetched.variant_id == ctx.variant_id
    assert fetched.spec_version_id == ctx.spec_version_id
    assert fetched.quota_reservation_id is None
    assert fetched.completed_at is None


async def test_settings_snapshot_round_trips(ctx: Context) -> None:
    request = _request(ctx, settings_snapshot={"model": "nano-banana-2"})

    await ctx.requests.add(request)

    fetched = await ctx.requests.get(ctx.tenant_id, request.id)
    assert fetched is not None
    assert fetched.settings_snapshot == {"model": "nano-banana-2"}
