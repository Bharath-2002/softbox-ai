"""Claims one `published` publication whose metrics are unset or stale,
for `agents.publication_metrics` to call `ChannelPublisher.fetch_metrics`
on outside this transaction. Claims a single row, not a batch — unlike the
`due_at` poller's reconciler shape, this involves an external call per
unit of work, the same `TaskQueue.claim`-style "one claim, one caller"
shape `StartPublicationPublish` already uses.

`mark_metrics_fetch_attempted()` bumps `metrics_fetched_at` in this same
transaction, before the provider call — a failed fetch (network error, a
since-deleted post, whatever) must not make the very next sweep
immediately re-select the same row; see that entity method's own
docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import PublicationId, TenantId

_DEFAULT_STALENESS = timedelta(hours=1)


@dataclass(frozen=True)
class MetricsFetchContext:
    publication_id: PublicationId
    external_post_id: str


class StartPublicationMetricsFetch:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, tenant_id: TenantId, *, staleness: timedelta = _DEFAULT_STALENESS
    ) -> MetricsFetchContext | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            publication = await uow.publications.claim_for_metrics_fetch(
                tenant_id, before=now - staleness
            )
            if publication is None:
                return None

            publication.mark_metrics_fetch_attempted(now=now)
            await uow.publications.update(publication)

            assert publication.external_post_id is not None  # guaranteed by the claim query
            return MetricsFetchContext(
                publication_id=publication.id,
                external_post_id=publication.external_post_id,
            )
