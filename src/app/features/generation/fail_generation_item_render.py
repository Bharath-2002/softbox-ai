"""Records a provider-side render failure (`generation_item`'s own
`running -> failed` edge) and asks `TaskQueue.fail` to decide retry-vs-dead
(D19: bounded retries, backoff, then a poison-message dead state). If the
job comes back `dead`, the item follows it into `dead` in the same
transaction — the two trackers must never disagree about whether this
attempt is still alive.
"""

from __future__ import annotations

from uuid import UUID

from app.entities.generation_item import GenerationItem
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import GenerationItemId, TenantId


class FailGenerationItemRender:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        item_id: GenerationItemId,
        job_id: UUID,
        error_code: str,
        error_detail: str,
    ) -> GenerationItem:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            item = await uow.generation_items.get(tenant_id, item_id)
            if item is None:
                raise NotFoundError("Generation item not found.")

            item.mark_failed(error_code=error_code, error_detail=error_detail)
            await uow.generation_items.update(item)

            new_job_status = await uow.task_queue.fail(
                tenant_id, job_id, error=f"{error_code}: {error_detail}", now=now
            )
            if new_job_status == "dead":
                item.mark_dead()
                await uow.generation_items.update(item)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="generation_item.failed",
                subject_type="generation_item",
                subject_id=item.id,
                before=None,
                after={"error_code": error_code, "status": item.status.value},
                now=now,
            )

            return item
