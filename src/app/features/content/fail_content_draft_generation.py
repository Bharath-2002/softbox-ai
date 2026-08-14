"""Records a `TextGeneration` provider failure and asks `TaskQueue.fail` to
decide retry-vs-dead (D19). Unlike `FailGenerationItemRender`, there is no
entity to update — `entities.content_draft` rows are only ever created on
success (`CompleteContentDraftGeneration`), so a provider failure here has
nothing to mark; the job's own `last_error` is the only record, same as any
other queue-execution failure this codebase tracks.
"""

from __future__ import annotations

from uuid import UUID

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId


class FailContentDraftGeneration:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, job_id: UUID, error_code: str, error_detail: str
    ) -> None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            await uow.task_queue.fail(
                tenant_id, job_id, error=f"{error_code}: {error_detail}", now=now
            )
