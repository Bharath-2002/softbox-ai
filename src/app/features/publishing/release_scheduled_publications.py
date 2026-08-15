"""D21's "`due_at` column plus a poller" half of scheduling (D21's own
words: "a task queue does not schedule reliably across restarts and
redeploys") — `publications.due_at` is the durable source of truth for
"when," and this sweep is the only thing that ever turns a due
`SCHEDULED` row into a claimable `publication.publish_requested` job.
Every publication goes through here, not just ones with a genuinely
future `due_at` — an immediate publish request is simply a row whose
`due_at` is already due.

Enqueues directly via `TaskQueue.enqueue`, not through `outbox_events` —
unlike every other "domain event happened, some other bounded context
should react" flow in this codebase, this sweep's entire job description
*is* queue management (D21: "a `due_at` column plus a poller" is the
alternative to letting the queue schedule itself), the same direct-queue
relationship `ReapStuckTaskQueueJobs`/`TaskQueue.reap_stuck` already have
with `task_queue_jobs`. Routing through the outbox would add an indirection
(and a second moving part, the relay) with no bounded context on the other
end to decouple from.

One transaction per tenant per sweep, bounded by `limit`, the same shape
`ReconcileGenerationRequestsForTenant` established: `list_due_for_release`
locks the rows it returns (`SKIP LOCKED`), so a second concurrent sweep
for the same tenant picks up whatever this one didn't reach rather than
double-releasing the same row.

Deliberately does **not** transition `status` off `SCHEDULED` here —
per `docs/DIAGRAMS.md`'s own state diagram, `scheduled -> dispatching`
happens when `StartPublicationPublish` actually claims the enqueued job,
not when this sweep merely creates it. Instead, `due_at` is pushed forward
by `_DISPATCH_GRACE` in the same transaction as the enqueue — the guard
against a *second* sweep re-enqueueing the same row before the first job
has been claimed. Without this, two sweeps a few minutes apart (nothing in
this codebase runs this route on an automatic timer yet; see the routers'
own "real capability, no automatic trigger" posture) would each see the
same `SCHEDULED`, still-due row and each enqueue a fresh job.
`_DISPATCH_GRACE` just needs to comfortably outlast the time between a job
being enqueued and being claimed under normal operation; if a worker is
down for longer than that, duplicate jobs can still accumulate, which is
wasteful but not unsafe — `mark_dispatching()` requires
`SCHEDULED`/`FAILED`, so a second claim of an already-`DISPATCHING`/
`PUBLISHED` row fails loudly rather than double-posting.
"""

from __future__ import annotations

from datetime import timedelta

from app.features.publishing.start_publication_publish import JOB_TYPE
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId

_DISPATCH_GRACE = timedelta(minutes=10)


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
                publication.defer_dispatch(until=now + _DISPATCH_GRACE, now=now)
                await uow.publications.update(publication)
                await uow.task_queue.enqueue(
                    tenant_id,
                    job_type=JOB_TYPE,
                    payload={"publication_id": str(publication.id)},
                    run_at=now,
                    now=now,
                )
                released += 1
        return released
