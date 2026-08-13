"""Implements ``app.services.ports.audit_log_repository.AuditLogRepository``.

Core queries against ``audit_log_table`` directly — no rich entity, same
shape as ``SqlPlatformAdminRepository`` and ``SqlIdempotencyRepository``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import audit_log_table
from app.services.ports.audit_log_repository import AuditLogEntry
from app.shared.ids import TenantId, UserId


class SqlAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        tenant_id: TenantId,
        *,
        actor_user_id: UserId | None,
        action: str,
        subject_type: str,
        subject_id: UUID,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip: str | None = None,
        now: datetime,
    ) -> None:
        stmt = insert(audit_log_table).values(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            before=before,
            after=after,
            ip=ip,
            occurred_at=now,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_for_subject(
        self, tenant_id: TenantId, subject_type: str, subject_id: UUID
    ) -> list[AuditLogEntry]:
        stmt = (
            select(audit_log_table)
            .where(
                audit_log_table.c.tenant_id == tenant_id,
                audit_log_table.c.subject_type == subject_type,
                audit_log_table.c.subject_id == subject_id,
            )
            .order_by(audit_log_table.c.occurred_at.desc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            AuditLogEntry(
                id=row.id,
                tenant_id=row.tenant_id,
                actor_user_id=row.actor_user_id,
                action=row.action,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                before=row.before,
                after=row.after,
                ip=str(row.ip) if row.ip is not None else None,
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]
