from __future__ import annotations

from datetime import UTC, datetime

from app.entities.tenant_domain import TenantDomain
from app.features.tenancy.list_tenant_domains import ListTenantDomains
from app.shared.ids import new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_lists_only_the_requested_tenants_domains() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    own = TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    other = TenantDomain.create(new_tenant_id(), "other.example.com", now=_NOW)
    await uow_factory.tenant_domains.add(own)
    await uow_factory.tenant_domains.add(other)
    use_case = ListTenantDomains(uow_factory)

    listed = await use_case(tenant_id=tenant_id)

    assert [d.id for d in listed] == [own.id]


async def test_an_unknown_tenant_has_no_domains() -> None:
    use_case = ListTenantDomains(FakeUnitOfWorkFactory())

    assert await use_case(tenant_id=new_tenant_id()) == []
