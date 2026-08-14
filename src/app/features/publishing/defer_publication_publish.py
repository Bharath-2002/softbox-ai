"""Rate-limited, not failed (D21). Completes the current job and enqueues
a fresh one for the same publication, scheduled past the exhausted rate
window, rather than routing the rejection through `FailPublicationPublish`.

That distinction matters more than it looks: `TaskQueue.fail()`'s bounded
retry ladder (`max_attempts=5`, backoff capped at 300s) exists for genuine
provider failures, where each retry is a real second chance. A per-account
rate limit resets on a fixed daily window, not on backoff — five rejected
attempts would exhaust inside roughly fifteen minutes (the backoff
ceiling), and the publication would go `dead`/`FAILED` while the window
that actually blocked it still had hours left to run. A channel at its cap
for the first hour of the day would silently lose every publish queued
for the rest of it. `Publication.defer()` reverts to `PENDING` and records
`last_error` for visibility without touching `attempts` — a rate limit is
"not yet," not "this failed."

No new `TaskQueue` port surface: `complete()` the claimed job, `enqueue()`
a new one for the same `publication_id`. The two are independent rows in
`task_queue_jobs` — the job that hit the rate limit really did complete
its work (deciding not to call the provider yet), and the fresh job is a
new claimable unit, not a retry of the old one.

Accepted, not fixed: this has no terminal state. A permanently
unsatisfiable limit (misconfigured to 0, or a tenant whose real volume
exceeds it every day) re-enqueues once per window forever rather than
ever failing loudly — the mirror image of the bug this design avoids.
That is the right tradeoff versus silently losing queued publishes, but
it means "deferred too many times, surface this to a human" has no owner
yet. The `due_at` poller (still ahead on M7's checklist) is the natural
place for that bound to live, once it exists.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.entities.publication import Publication
from app.features.publishing.start_publication_publish import JOB_TYPE
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import PublicationId, TenantId


class DeferPublicationPublish:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        publication_id: PublicationId,
        job_id: UUID,
        reason: str,
        run_at: datetime,
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            publication.defer(reason=reason, now=now)
            await uow.publications.update(publication)

            await uow.task_queue.complete(tenant_id, job_id, now=now)
            await uow.task_queue.enqueue(
                tenant_id,
                job_type=JOB_TYPE,
                payload={"publication_id": str(publication.id)},
                run_at=run_at,
                now=now,
            )

            return publication
