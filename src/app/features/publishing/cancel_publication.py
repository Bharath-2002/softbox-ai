"""Human-driven cancellation of a still-`SCHEDULED` publication (D21's
diagram: `scheduled -> cancelled`, the only edge out of `scheduled` besides
the `due_at` poller's own). Requires `SCHEDULED` specifically —
`Publication.cancel()` raises otherwise, so a post already `DISPATCHING`
or later cannot be pulled back once a provider call may be in flight.
"""

from __future__ import annotations

from app.entities.publication import Publication
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import PublicationId, TenantId, UserId


class CancelPublication:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, publication_id: PublicationId, cancelled_by: UserId
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            before_status = publication.status.value
            publication.cancel(now=now)
            await uow.publications.update(publication)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=cancelled_by,
                action="publication.cancelled",
                subject_type="publication",
                subject_id=publication.id,
                before={"status": before_status},
                after={"status": publication.status.value},
                now=now,
            )

            return publication
