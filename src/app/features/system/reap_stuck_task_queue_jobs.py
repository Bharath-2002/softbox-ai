"""The other half of D19's "reconciler sweeps due, stuck and retryable
runs" — `claim()`/`fail()` alone only recover a job whose worker calls
back in; nothing else notices a worker that crashed or was killed
mid-job, leaving its claim `running` forever. Single-tenant,
single-transaction, same shape as `RelayOutboxEventsForTenant` — a
generic cross-tenant driver is deliberately not built alongside this,
matching that file's own precedent of shipping the per-tenant unit first
and generalising only once a real caller needs the sweep.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.task_backoff import STUCK_JOB_THRESHOLD
from app.shared.clock import Clock
from app.shared.ids import TenantId


class ReapStuckTaskQueueJobs:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, tenant_id: TenantId) -> int:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            return await uow.task_queue.reap_stuck(
                tenant_id, claimed_before=now - STUCK_JOB_THRESHOLD, now=now
            )
