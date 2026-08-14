"""Records a failed `ChannelPublisher.publish`/`validate` call and asks
`TaskQueue.fail` to decide retry-vs-dead. If the job comes back `dead`,
`Publication.record_attempt_failure(terminal=True)` moves the row to its
own terminal `FAILED` state in the same transaction — the two trackers
must never disagree about whether another attempt is still coming, the
same discipline `FailGenerationItemRender` already established for
`generation_items`/`dead`.
"""

from __future__ import annotations

from uuid import UUID

from app.entities.publication import Publication
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import PublicationId, TenantId


class FailPublicationPublish:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, publication_id: PublicationId, job_id: UUID, error: str
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            new_job_status = await uow.task_queue.fail(tenant_id, job_id, error=error, now=now)
            publication.record_attempt_failure(
                error=error, terminal=(new_job_status == "dead"), now=now
            )
            await uow.publications.update(publication)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="publication.attempt_failed",
                subject_type="publication",
                subject_id=publication.id,
                before=None,
                after={"status": publication.status.value, "attempts": publication.attempts},
                now=now,
            )

            return publication
