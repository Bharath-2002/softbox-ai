"""Records a QC **job execution** failure - the provider/storage call itself
raising, not a verdict the provider returned. Asks `TaskQueue.fail` to
decide retry-vs-dead the same way `FailGenerationItemRender` does; unlike
that use case, no domain entity follows the job into a terminal state on
`dead` - `CatalogImage` has no `qc_dead`, since a QC job that permanently
can't run is an operational problem (the provider is down), not a fact
about the image's quality. The image stays `pending_qc` either way, ready
to be reclaimed once the job is retried or the underlying problem is fixed.
"""

from __future__ import annotations

from uuid import UUID

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId


class FailCatalogImageQc:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId, job_id: UUID, error: str) -> None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            await uow.task_queue.fail(tenant_id, job_id, error=error, now=now)
