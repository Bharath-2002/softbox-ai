from __future__ import annotations

from datetime import UTC, datetime

from app.features.system.relay_outbox_events import RelayOutboxEvents
from app.features.system.relay_outbox_events_for_tenant import RelayOutboxEventsForTenant
from app.shared.ids import new_tenant_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[RelayOutboxEvents, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    relay_for_tenant = RelayOutboxEventsForTenant(uow_factory, FakeClock(_NOW))
    return RelayOutboxEvents(uow_factory, relay_for_tenant), uow_factory


async def test_relaying_with_no_active_tenants_does_nothing() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case() == {}


async def test_relaying_covers_every_active_tenant() -> None:
    use_case, uow_factory = _use_case()
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    uow_factory.tenants.active_tenant_ids = [tenant_a, tenant_b]
    await uow_factory.outbox_events.add(tenant_a, event_type="a", payload={}, now=_NOW)
    await uow_factory.outbox_events.add(tenant_b, event_type="b", payload={}, now=_NOW)
    await uow_factory.outbox_events.add(tenant_b, event_type="c", payload={}, now=_NOW)

    counts = await use_case()

    assert counts == {tenant_a: 1, tenant_b: 2}


async def test_a_failing_tenant_does_not_stop_the_others() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    uow_factory.tenants.active_tenant_ids = [tenant_a, tenant_b]
    await uow_factory.outbox_events.add(tenant_b, event_type="b", payload={}, now=_NOW)
    real_relay_for_tenant = RelayOutboxEventsForTenant(uow_factory, FakeClock(_NOW))

    async def _relay_for_tenant(tenant_id: object, *, limit: int = 50) -> int:
        if tenant_id == tenant_a:
            raise RuntimeError("boom")
        return await real_relay_for_tenant(tenant_id, limit=limit)

    use_case = RelayOutboxEvents(uow_factory, _relay_for_tenant)

    counts = await use_case()

    assert counts == {tenant_a: 0, tenant_b: 1}
