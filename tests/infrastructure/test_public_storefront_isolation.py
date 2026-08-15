"""M8's Gate, proven against real Postgres with the non-owner ``softbox_app``
role — not the fake-backed router tests in ``tests/test_public_router.py``.

Those router tests use ``FakeUnitOfWorkFactory``; ``InMemoryProductRepository``
is keyed by ``(tenant_id, product_id)``, so a fake-backed 404 there proves
only that the dict lookup missed, not that a real ``WHERE tenant_id =``
clause or RLS policy is what stood between tenant A's request and tenant
B's row. CLAUDE.md §10 is explicit that isolation must be proven under the
app role, and that a test must assert the row exists for tenant B before
asserting it is invisible as tenant A — a passing test against an empty
table proves nothing.

Two hops, both real: ``SqlTenantDomainRepository.resolve_by_hostname`` runs
with no tenant bound (the resolver's whole point), then a second,
tenant-scoped ``app_uow`` — the same two-transaction shape
``api/deps/tenant_resolution.py`` and the public router actually use —
fetches the product RLS is supposed to hide.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from sqlalchemy import text

from app.entities.product import Product, ProductStatus
from app.entities.tenant_domain import TenantDomain
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import (
    CategoryId,
    CategorySpecVersionId,
    TenantId,
    UserId,
    new_category_id,
    new_category_spec_version_id,
    new_tenant_id,
    new_user_id,
)

pytestmark = pytest.mark.db

UowFactory = Callable[[TenantId | None], SqlUnitOfWork]


@dataclass
class _TenantFixture:
    tenant_id: TenantId
    category_id: CategoryId
    spec_version_id: CategorySpecVersionId
    user_id: UserId


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


async def _seed_publishable_tenant(owner_uow: UowFactory) -> _TenantFixture:
    """A tenant plus everything a real ``Product`` row's composite FKs
    require — category, spec version, user — the same fixture shape
    ``test_product_repository_contract.py`` already established."""
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    spec_version_id = new_category_spec_version_id()
    user_id = new_user_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
        await uow.session.execute(
            _INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )
    # categories/category_spec_versions are FORCE-RLS - even the owner role
    # needs the tenant GUC bound, which owner_uow(tenant_id) does in
    # __aenter__ (the same reason the sibling contract test SET LOCALs
    # manually on its own raw session).
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
    return _TenantFixture(
        tenant_id=tenant_id,
        category_id=category_id,
        spec_version_id=spec_version_id,
        user_id=user_id,
    )


async def test_resolving_tenant_as_host_never_surfaces_tenant_bs_product(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_a = await _seed_publishable_tenant(owner_uow)
    tenant_b = await _seed_publishable_tenant(owner_uow)
    hostname = f"a-{tenant_a.tenant_id.hex[:12]}.example.com"

    async with app_uow(tenant_a.tenant_id) as uow:
        await uow.tenant_domains.add(
            TenantDomain.create(tenant_a.tenant_id, hostname, now=utcnow())
        )

    product = Product.create(
        tenant_b.tenant_id,
        tenant_b.category_id,
        tenant_b.spec_version_id,
        attributes={},
        created_by=tenant_b.user_id,
        now=utcnow(),
        title="Tenant B's saree",
    )
    product.status = ProductStatus.PUBLISHED
    async with app_uow(tenant_b.tenant_id) as uow:
        await uow.products.add(product)

    # The row genuinely exists for tenant B - a passing assertion below
    # would prove nothing if this table were simply empty (CLAUDE.md §10).
    async with app_uow(tenant_b.tenant_id) as uow:
        assert await uow.products.get(tenant_b.tenant_id, product.id) is not None

    # Hop 1: resolve the host with no tenant bound - the resolver's job.
    async with app_uow(None) as uow:
        resolved = await uow.tenant_domains.resolve_by_hostname(hostname)
    assert resolved is not None
    assert resolved.tenant_id == tenant_a.tenant_id

    # Hop 2: a real, tenant-A-scoped transaction asks for tenant B's known
    # product id - the exact scenario M8's Gate names.
    async with app_uow(resolved.tenant_id) as uow:
        fetched = await uow.products.get(resolved.tenant_id, product.id)

    assert fetched is None
