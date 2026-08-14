"""Claims the next due `publication.publish_requested` job and hands back
everything `agents.publish_channel` needs for the `ChannelPublisher.publish`
call it makes *outside* this transaction — the composed payload and, most
importantly, the row's own `idempotency_key`, read here rather than
regenerated, which is what makes a retry reuse the exact key `publish()`
needs to recognise it already ran.

A missing `publication` (the job's payload points at a row that no longer
exists) is a data inconsistency, not a retryable provider failure — dead-
lettered via `TaskQueue.fail` immediately, the same posture
`StartGenerationItemRender`/`StartContentDraftGeneration` both already
apply to their own "payload references something now gone" case.

`mark_publishing()` accepts the row's first attempt (`PENDING`, the normal
case) or a retry after a reverted failed attempt (also `PENDING` — see
`entities.publication`'s docstring for why a failed-but-retryable attempt
reverts to `PENDING` rather than its own transient state).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import ProductVariantId, PublicationId, SocialAccountId, TenantId

JOB_TYPE = "publication.publish_requested"
CLAIMED_BY = "publish-channel-worker"


@dataclass(frozen=True)
class PublicationPublishContext:
    job_id: UUID
    publication_id: PublicationId
    variant_id: ProductVariantId
    channel_id: SocialAccountId
    idempotency_key: str
    payload: dict[str, Any]


class StartPublicationPublish:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId) -> PublicationPublishContext | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            job = await uow.task_queue.claim(
                tenant_id, claimed_by=CLAIMED_BY, job_type=JOB_TYPE, now=now
            )
            if job is None:
                return None

            publication_id = PublicationId(UUID(job.payload["publication_id"]))
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                await uow.task_queue.fail(
                    tenant_id, job.id, error=f"publication {publication_id} not found", now=now
                )
                return None

            publication.mark_publishing(now=now)
            await uow.publications.update(publication)

            return PublicationPublishContext(
                job_id=job.id,
                publication_id=publication.id,
                variant_id=publication.variant_id,
                channel_id=publication.channel_id,
                idempotency_key=publication.idempotency_key,
                payload=publication.payload,
            )
