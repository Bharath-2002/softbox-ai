from __future__ import annotations

from datetime import UTC, datetime

from app.features.tenancy.register_tenant_domain import RegisterTenantDomain
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[RegisterTenantDomain, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return RegisterTenantDomain(uow_factory, FakeClock(_NOW)), uow_factory


async def test_registering_a_domain_persists_it_normalised() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()

    domain = await use_case(
        tenant_id=tenant_id, hostname="Shop.Example.COM", actor_user_id=new_user_id()
    )

    assert domain.hostname == "shop.example.com"
    stored = await uow_factory.tenant_domains.get(tenant_id, domain.id)
    assert stored is not None and stored.hostname == "shop.example.com"


async def test_registration_is_audited() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()

    domain = await use_case(
        tenant_id=tenant_id, hostname="shop.example.com", actor_user_id=actor_id
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "tenant_domain", domain.id)
    assert entries[0].action == "tenant_domain.registered"
    assert entries[0].actor_user_id == actor_id
