"""The relay D19 calls for: reads one tenant's unpublished `outbox_events`
and turns each into a `task_queue_jobs` row, marking the event published —
**one transaction**, so a crash mid-relay never double-enqueues a job it
already committed, nor loses an event it already marked published (the same
"committed but never enqueued" gap the outbox exists to close applies
symmetrically to the relay itself).

`job_type` is the event's own `event_type`, verbatim — a queued job is
simply "the work that responds to this domain event having happened," and
inventing a translation layer between the two names would be a second way
to say the same thing for no caller that needs it yet.

Single-tenant, single-transaction, by design — the same "one use case, one
transaction" rule every other `features` module follows. Looping every
tenant is a separate concern (`RelayOutboxEvents`, this package), which
calls this once per tenant rather than folding the loop in here.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId


class RelayOutboxEventsForTenant:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, tenant_id: TenantId, *, limit: int = 50) -> int:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            events = await uow.outbox_events.list_unpublished(tenant_id, limit=limit)
            for event in events:
                await uow.task_queue.enqueue(
                    tenant_id,
                    job_type=event.event_type,
                    payload=event.payload,
                    run_at=now,
                    now=now,
                )
                await uow.outbox_events.mark_published(tenant_id, event.id, now=now)
            return len(events)
