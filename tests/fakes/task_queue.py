from __future__ import annotations

import random
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from app.services.ports.task_queue import TaskQueueJob
from app.services.task_backoff import compute_backoff
from app.shared.ids import TenantId


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._rows: dict[UUID, TaskQueueJob] = {}

    async def enqueue(
        self,
        tenant_id: TenantId,
        *,
        job_type: str,
        payload: dict[str, Any],
        run_at: datetime,
        now: datetime,
        max_attempts: int = 5,
    ) -> UUID:
        job_id = uuid.uuid4()
        self._rows[job_id] = TaskQueueJob(
            id=job_id,
            tenant_id=tenant_id,
            job_type=job_type,
            payload=payload,
            status="pending",
            attempts=0,
            max_attempts=max_attempts,
            run_at=run_at,
            claimed_at=None,
            claimed_by=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        return job_id

    async def claim(
        self,
        tenant_id: TenantId,
        *,
        claimed_by: str,
        job_type: str | None = None,
        now: datetime,
    ) -> TaskQueueJob | None:
        candidates = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.status == "pending"
            and row.run_at <= now
            and (job_type is None or row.job_type == job_type)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda row: row.run_at)
        claimed = replace(
            candidates[0], status="running", claimed_at=now, claimed_by=claimed_by, updated_at=now
        )
        self._rows[claimed.id] = claimed
        return claimed

    async def get(self, tenant_id: TenantId, job_id: UUID) -> TaskQueueJob | None:
        row = self._rows.get(job_id)
        return row if row is not None and row.tenant_id == tenant_id else None

    async def complete(self, tenant_id: TenantId, job_id: UUID, *, now: datetime) -> None:
        row = await self.get(tenant_id, job_id)
        if row is not None:
            self._rows[job_id] = replace(row, status="succeeded", updated_at=now)

    async def fail(self, tenant_id: TenantId, job_id: UUID, *, error: str, now: datetime) -> str:
        row = await self.get(tenant_id, job_id)
        if row is None:
            raise ValueError(f"Task queue job {job_id} not found for tenant {tenant_id}.")

        new_attempts = row.attempts + 1
        if new_attempts >= row.max_attempts:
            self._rows[job_id] = replace(
                row, status="dead", attempts=new_attempts, last_error=error, updated_at=now
            )
            return "dead"

        delay = compute_backoff(new_attempts, jitter=random.random())
        self._rows[job_id] = replace(
            row,
            status="pending",
            attempts=new_attempts,
            last_error=error,
            run_at=now + delay,
            updated_at=now,
        )
        return "pending"

    async def reap_stuck(
        self, tenant_id: TenantId, *, claimed_before: datetime, now: datetime
    ) -> int:
        stuck = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id
            and row.status == "running"
            and row.claimed_at is not None
            and row.claimed_at < claimed_before
        ]
        for row in stuck:
            await self.fail(
                tenant_id,
                row.id,
                error=f"Job stayed 'running' past {claimed_before.isoformat()} "
                "without completing or failing — its worker likely crashed.",
                now=now,
            )
        return len(stuck)
