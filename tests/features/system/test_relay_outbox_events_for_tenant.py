from __future__ import annotations

from datetime import UTC, datetime

from app.features.system.relay_outbox_events_for_tenant import RelayOutboxEventsForTenant
from app.shared.ids import new_tenant_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[RelayOutboxEventsForTenant, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return RelayOutboxEventsForTenant(uow_factory, FakeClock(_NOW)), uow_factory


async def test_relaying_with_nothing_unpublished_relays_zero() -> None:
    use_case, _uow_factory = _use_case()

    count = await use_case(new_tenant_id())

    assert count == 0


async def test_relaying_enqueues_a_job_and_marks_the_event_published() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    await uow_factory.outbox_events.add(
        tenant_id, event_type="product.created", payload={"id": "abc"}, now=_NOW
    )

    count = await use_case(tenant_id)

    assert count == 1
    assert await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10) == []
    claimed = await uow_factory.task_queue.claim(tenant_id, claimed_by="test", now=_NOW)
    assert claimed is not None
    assert claimed.job_type == "product.created"
    assert claimed.payload == {"id": "abc"}


async def test_relaying_respects_the_limit() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    for i in range(3):
        await uow_factory.outbox_events.add(
            tenant_id, event_type=f"event-{i}", payload={}, now=_NOW
        )

    count = await use_case(tenant_id, limit=2)

    assert count == 2
    assert len(await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)) == 1
