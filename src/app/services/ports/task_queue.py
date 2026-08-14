"""The Postgres-backed job queue (D19) — a durable work list, not a rich
domain object (same "stored ticket" shape as `OutboxEventRepository`).

`claim()` is tenant-scoped, like every port in this codebase (D9) — not a
cross-tenant sweep. See the `task_queue_jobs` migration's module docstring
for why: RLS is forced on this table exactly like every other tenant-scoped
one, so an unscoped claim query would see zero rows regardless of which
tenant a job belongs to. A worker process (not built in this chunk) is
expected to loop the tenant list and claim per tenant per poll cycle.

`fail()` decides retry-vs-dead internally (bounded retries, D19) rather than
taking a caller-supplied `next_run_at` — pushing that policy onto every
future caller guarantees two callers eventually disagree about backoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.ids import TenantId


@dataclass(frozen=True)
class TaskQueueJob:
    id: UUID
    tenant_id: TenantId
    job_type: str
    payload: dict[str, Any]
    status: str
    attempts: int
    max_attempts: int
    run_at: datetime
    claimed_at: datetime | None
    claimed_by: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class TaskQueue(Protocol):
    async def enqueue(
        self,
        tenant_id: TenantId,
        *,
        job_type: str,
        payload: dict[str, Any],
        run_at: datetime,
        now: datetime,
        max_attempts: int = 5,
    ) -> UUID: ...

    async def claim(
        self, tenant_id: TenantId, *, claimed_by: str, now: datetime
    ) -> TaskQueueJob | None:
        """Atomically locks and claims the oldest-due `pending` job with
        `run_at <= now`, in one statement — never a separate lock-then-update
        round trip. `None` if nothing is claimable right now."""
        ...

    async def get(self, tenant_id: TenantId, job_id: UUID) -> TaskQueueJob | None: ...

    async def complete(self, tenant_id: TenantId, job_id: UUID, *, now: datetime) -> None: ...

    async def fail(self, tenant_id: TenantId, job_id: UUID, *, error: str, now: datetime) -> None:
        """Increments `attempts`. Below `max_attempts`, reschedules
        `pending` with an exponential-backoff-with-jitter `run_at`
        (`services.task_backoff.compute_backoff`); at or beyond it,
        transitions to the terminal `dead` state with `error` preserved as
        `last_error` — D19's "poison-message handling"."""
        ...
