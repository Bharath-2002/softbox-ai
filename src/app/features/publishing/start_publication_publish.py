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

A publication that exists but is not in a claimable status (`SCHEDULED`
or `FAILED`) gets the same dead-letter treatment, rather than calling
`mark_dispatching()` and letting its `ValidationError` propagate uncaught
out of the worker step. This is a real, reachable path, not a defensive
guess: `CancelPublication` requires only `SCHEDULED`, so a cancel can land
in the window between the `due_at` poller enqueueing this job and this
use case claiming it — an advisor pass caught this before it shipped.

`mark_dispatching()` accepts the row's first attempt (`SCHEDULED`, its
`due_at` poller-released job) or a retry (`FAILED`, its `TaskQueue`
backoff-rescheduled job — a retry never goes back through `SCHEDULED`;
see `entities.publication`'s docstring).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.entities.publication import PublicationStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import ProductVariantId, PublicationId, SocialAccountId, TenantId

JOB_TYPE = "publication.publish_requested"
CLAIMED_BY = "publish-channel-worker"
_CLAIMABLE_STATUSES = (PublicationStatus.SCHEDULED, PublicationStatus.FAILED)


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

            if publication.status not in _CLAIMABLE_STATUSES:
                await uow.task_queue.fail(
                    tenant_id,
                    job.id,
                    error=(
                        f"publication {publication_id} is "
                        f"{publication.status.value!r}, not claimable"
                    ),
                    now=now,
                )
                return None

            publication.mark_dispatching(now=now)
            await uow.publications.update(publication)

            return PublicationPublishContext(
                job_id=job.id,
                publication_id=publication.id,
                variant_id=publication.variant_id,
                channel_id=publication.channel_id,
                idempotency_key=publication.idempotency_key,
                payload=publication.payload,
            )
