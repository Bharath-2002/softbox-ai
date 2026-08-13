"""Write path for ``audit_log`` (D3, chunk 3's ``ca5759119d91`` migration).

Append-only — no update, no delete method on this port. An audit trail that
can be edited after the fact is not one.

No real consumer yet: every mutating use case built so far (``CompleteLogin``,
``RefreshSession``, ``Logout``, and the bootstrap-admin grant) is
tenant-agnostic, while ``audit_log`` is a tenant-scoped, RLS-forced table.
The mechanism is proven end to end against real Postgres here; its first
real caller lands with M2's tenant-scoped mutations (category/spec edits).

``now`` is a caller-supplied parameter, not read internally — the same shape
as ``PlatformAdminRepository.grant``, so a use case's own injected ``Clock``
is the single source of "when," not a second one hidden in this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.ids import TenantId, UserId


@dataclass(frozen=True)
class AuditLogEntry:
    id: UUID
    tenant_id: TenantId
    actor_user_id: UserId | None
    action: str
    subject_type: str
    subject_id: UUID
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    occurred_at: datetime


class AuditLogRepository(Protocol):
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
    ) -> None: ...

    async def list_for_subject(
        self, tenant_id: TenantId, subject_type: str, subject_id: UUID
    ) -> list[AuditLogEntry]:
        """Newest first — the natural order for "what happened to this
        thing" review, which is the only reason this port has a read
        method at all."""
        ...
