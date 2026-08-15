"""Records a successful `ChannelPublisher.fetch_metrics` result — the
second half of `agents.publication_metrics`'s two-transaction shape,
mirroring `CompletePublicationPublish`. No status transition: metrics are
a snapshot on an already-`PUBLISHED` row, not a state change.
"""

from __future__ import annotations

from dataclasses import asdict

from app.entities.publication import Publication
from app.services.ports.channel_publisher import ChannelMetrics
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import PublicationId, TenantId


class CompletePublicationMetricsFetch:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, publication_id: PublicationId, metrics: ChannelMetrics
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.get(tenant_id, publication_id)
            if publication is None:
                raise NotFoundError("Publication not found.")

            publication.record_metrics(metrics=asdict(metrics), now=now)
            await uow.publications.update(publication)

            return publication
