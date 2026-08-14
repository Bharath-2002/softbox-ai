"""Implements ``app.services.ports.task_queue.TaskQueue``.

Core queries against ``task_queue_jobs_table`` directly — no rich entity,
same shape as ``SqlOutboxEventRepository``.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import task_queue_jobs_table
from app.services.ports.task_queue import TaskQueueJob
from app.services.task_backoff import compute_backoff
from app.shared.ids import TenantId


def _to_job(row: Any) -> TaskQueueJob:
    return TaskQueueJob(
        id=row.id,
        tenant_id=row.tenant_id,
        job_type=row.job_type,
        payload=row.payload,
        status=row.status,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        run_at=row.run_at,
        claimed_at=row.claimed_at,
        claimed_by=row.claimed_by,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlTaskQueue:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        stmt = insert(task_queue_jobs_table).values(
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
        await self._session.execute(stmt)
        await self._session.flush()
        return job_id

    async def claim(
        self,
        tenant_id: TenantId,
        *,
        claimed_by: str,
        job_type: str | None = None,
        now: datetime,
    ) -> TaskQueueJob | None:
        candidate = (
            select(task_queue_jobs_table.c.id)
            .where(
                task_queue_jobs_table.c.tenant_id == tenant_id,
                task_queue_jobs_table.c.status == "pending",
                task_queue_jobs_table.c.run_at <= now,
            )
            .order_by(task_queue_jobs_table.c.run_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job_type is not None:
            candidate = candidate.where(task_queue_jobs_table.c.job_type == job_type)
        stmt = (
            update(task_queue_jobs_table)
            .where(task_queue_jobs_table.c.id == candidate.scalar_subquery())
            .values(status="running", claimed_at=now, claimed_by=claimed_by, updated_at=now)
            .returning(task_queue_jobs_table)
        )
        row = (await self._session.execute(stmt)).one_or_none()
        await self._session.flush()
        return _to_job(row) if row is not None else None

    async def get(self, tenant_id: TenantId, job_id: UUID) -> TaskQueueJob | None:
        stmt = select(task_queue_jobs_table).where(
            task_queue_jobs_table.c.tenant_id == tenant_id,
            task_queue_jobs_table.c.id == job_id,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return _to_job(row) if row is not None else None

    async def complete(self, tenant_id: TenantId, job_id: UUID, *, now: datetime) -> None:
        stmt = (
            update(task_queue_jobs_table)
            .where(
                task_queue_jobs_table.c.tenant_id == tenant_id,
                task_queue_jobs_table.c.id == job_id,
            )
            .values(status="succeeded", updated_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def fail(self, tenant_id: TenantId, job_id: UUID, *, error: str, now: datetime) -> str:
        job = await self.get(tenant_id, job_id)
        if job is None:
            raise ValueError(f"Task queue job {job_id} not found for tenant {tenant_id}.")

        new_attempts = job.attempts + 1
        new_status = "dead" if new_attempts >= job.max_attempts else "pending"
        if new_status == "dead":
            values: dict[str, Any] = {
                "status": "dead",
                "attempts": new_attempts,
                "last_error": error,
            }
        else:
            delay = compute_backoff(new_attempts, jitter=random.random())
            values = {
                "status": "pending",
                "attempts": new_attempts,
                "last_error": error,
                "run_at": now + delay,
            }

        stmt = (
            update(task_queue_jobs_table)
            .where(
                task_queue_jobs_table.c.tenant_id == tenant_id,
                task_queue_jobs_table.c.id == job_id,
            )
            .values(**values, updated_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return new_status
