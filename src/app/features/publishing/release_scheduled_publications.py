"""D21's "`due_at` column plus a poller" half of scheduling — the queue
itself does not schedule reliably across restarts and redeploys, so the
source of truth for "when" stays `publications.scheduled_at`, and this
sweep is what turns a due `SCHEDULED` row into a claimable one.

One transaction per tenant per sweep, bounded by `limit`, the same shape
`ReconcileGenerationRequestsForTenant` established: `list_due_for_release`
locks the rows it returns (`SKIP LOCKED`), so a second concurrent sweep for
the same tenant picks up whatever this one didn't reach rather than
double-releasing the same row. `release_for_publishing()` and the
`publish_requested` outbox write happen together, in the row's own
transition transaction — exactly the "commit the row and its trigger
together" shape `CreatePublication` already uses for a publication that
was never scheduled at all.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId

_EVENT_TYPE = "publication.publish_requested"


class ReleaseScheduledPublicationsForTenant:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, tenant_id: TenantId, *, limit: int = 50) -> int:
        now = self._clock.now()
        released = 0
        async with self._uow_factory(tenant_id) as uow:
            due = await uow.publications.list_due_for_release(tenant_id, before=now, limit=limit)
            for publication in due:
                publication.release_for_publishing(now=now)
                await uow.publications.update(publication)
                await uow.outbox_events.add(
                    tenant_id,
                    event_type=_EVENT_TYPE,
                    payload={"publication_id": str(publication.id)},
                    now=now,
                )
                released += 1
        return released
