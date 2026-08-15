"""Two properties `test_tenant_domain_repository_contract.py`'s single-tenant
`ctx` fixture cannot exercise: `UNIQUE (hostname)` across two real tenants,
and `list_for_tenant` actually excluding another tenant's row rather than
merely never having been asked to include one.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.entities.tenant_domain import TenantDomain
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _seed_tenant(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork], tenant_id: TenantId
) -> None:
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )


async def test_two_tenants_cannot_claim_the_same_hostname(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    await _seed_tenant(owner_uow, tenant_a)
    await _seed_tenant(owner_uow, tenant_b)
    # owner_uow commits real rows with no rollback wrapper (CLAUDE.md §10) -
    # a literal hostname would collide with itself on the very next test run.
    hostname = f"shop-{tenant_a.hex[:12]}.example.com"

    async with owner_uow(tenant_a) as uow:
        await uow.tenant_domains.add(TenantDomain.create(tenant_a, hostname, now=utcnow()))

    with pytest.raises(IntegrityError, match="uq_tenant_domains_hostname"):
        async with owner_uow(tenant_b) as uow:
            await uow.tenant_domains.add(TenantDomain.create(tenant_b, hostname, now=utcnow()))


async def test_list_for_tenant_excludes_another_tenants_domain(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    await _seed_tenant(owner_uow, tenant_a)
    await _seed_tenant(owner_uow, tenant_b)

    async with owner_uow(tenant_a) as uow:
        own = TenantDomain.create(
            tenant_a, f"a-shop-{tenant_a.hex[:12]}.example.com", now=utcnow()
        )
        await uow.tenant_domains.add(own)
    async with owner_uow(tenant_b) as uow:
        await uow.tenant_domains.add(
            TenantDomain.create(tenant_b, f"b-shop-{tenant_b.hex[:12]}.example.com", now=utcnow())
        )

    async with owner_uow(tenant_a) as uow:
        listed = await uow.tenant_domains.list_for_tenant(tenant_a)

    assert [d.id for d in listed] == [own.id]
