from __future__ import annotations

from datetime import UTC, datetime

from app.entities.tenant_domain import TenantDomain
from app.features.tenancy.resolve_tenant_from_host import ResolveTenantFromHost
from app.shared.ids import new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_resolves_a_registered_hostname_to_its_tenant() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )
    use_case = ResolveTenantFromHost(uow_factory)

    assert await use_case(hostname="shop.example.com") == tenant_id


async def test_an_unregistered_hostname_resolves_to_none() -> None:
    use_case = ResolveTenantFromHost(FakeUnitOfWorkFactory())

    assert await use_case(hostname="unknown.example.com") is None
