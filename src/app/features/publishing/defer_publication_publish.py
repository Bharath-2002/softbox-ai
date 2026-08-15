"""Rate-limited, not failed (D21). Completes the current job and pushes
the publication's `due_at` forward to the window's actual end, rather than
routing the rejection through `FailPublicationPublish` or (the pre-rework
version's mistake) directly `enqueue()`-ing a fresh `TaskQueue` job for
the deferred time — that is exactly the "hand a task queue a schedule to
keep" anti-pattern D21 warns against ("a task queue does not schedule
reliably across restarts and redeploys"), just for the rate-limit-defer
case instead of the first dispatch. `Publication.defer()` reverts
`DISPATCHING -> SCHEDULED` and sets `due_at`; the `due_at` poller
(`features.publishing.release_scheduled_publications`) is what picks the
row back up once due, the same mechanism every other `SCHEDULED` row goes
through — one scheduling path, not two.

That distinction (deferred vs failed) matters more than it looks:
`TaskQueue.fail()`'s bounded retry ladder (`max_attempts=5`, backoff
capped at 300s) exists for genuine provider failures, where each retry is
a real second chance. A per-account rate limit resets on a fixed daily
window, not on backoff — five rejected attempts would exhaust inside
roughly fifteen minutes (the backoff ceiling), and the publication would
go `dead` while the window that actually blocked it still had hours left
to run. A channel at its cap for the first hour of the day would silently
lose every publish queued for the rest of it. `defer()` records
`last_error` for visibility without touching `attempts` — a rate limit is
"not yet," not "this failed."

Accepted, not fixed: this has no terminal state. A permanently
unsatisfiable limit (misconfigured to 0, or a tenant whose real volume
exceeds it every day) cycles `scheduled -> dispatching -> deferred ->
scheduled` forever rather than ever failing loudly — the mirror image of
the bug this design avoids. That is the right tradeoff versus silently
losing queued publishes, but it means "deferred too many times, surface
this to a human" has no owner yet.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.entities.publication import Publication
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
        due_at: datetime,
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            publication.defer(reason=reason, due_at=due_at, now=now)
            await uow.publications.update(publication)

            await uow.task_queue.complete(tenant_id, job_id, now=now)

            return publication
