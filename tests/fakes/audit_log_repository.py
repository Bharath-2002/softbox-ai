from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.services.ports.audit_log_repository import AuditLogEntry
from app.shared.ids import TenantId, UserId


class InMemoryAuditLogRepository:
    def __init__(self) -> None:
        self._rows: list[AuditLogEntry] = []

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
        self._rows.append(
            AuditLogEntry(
                id=uuid4(),
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
        )

    async def list_for_subject(
        self, tenant_id: TenantId, subject_type: str, subject_id: UUID
    ) -> list[AuditLogEntry]:
        matches = [
            row
            for row in self._rows
            if row.tenant_id == tenant_id
            and row.subject_type == subject_type
            and row.subject_id == subject_id
        ]
        return sorted(matches, key=lambda row: row.occurred_at, reverse=True)
