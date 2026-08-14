"""Records a successful `ChannelPublisher.publish` result and completes
the job — the second half of `agents.publish_channel`'s two-transaction
shape, mirroring `CompleteGenerationItemRender`/`CompleteCatalogImageQc`.
"""

from __future__ import annotations

from uuid import UUID

from app.entities.publication import Publication
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import PublicationId, TenantId


class CompletePublicationPublish:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        publication_id: PublicationId,
        job_id: UUID,
        external_post_id: str,
        permalink: str | None,
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            publication.mark_published(
                external_post_id=external_post_id, permalink=permalink, now=now
            )
            await uow.publications.update(publication)

            await uow.task_queue.complete(tenant_id, job_id, now=now)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="publication.published",
                subject_type="publication",
                subject_id=publication.id,
                before=None,
                after={"status": publication.status.value, "external_post_id": external_post_id},
                now=now,
            )

            return publication
