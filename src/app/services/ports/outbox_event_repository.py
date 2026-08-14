"""The transactional outbox (D19, M5). A domain event is written here in the
same transaction as the state change it describes — the reliability
primitive that closes the "committed but never enqueued" gap: a use case
that enqueues work by calling an external system directly can commit its
own state change and then crash (or roll back) before the external call
lands, or vice versa. Writing to this table instead is the same Postgres
transaction as the state change, so both succeed or both roll back
together. A relay (not built in this chunk — see CHECKLIST) reads
unpublished rows afterwards and turns them into whatever they need to
become: a `TaskQueue` job, a webhook, nothing yet.

No rich `OutboxEvent` domain object — this is a stored delivery ticket, the
same "not a rich domain object" shape `IdempotencyRepository`/
`PlatformAdminRepository` already use, not a `Product`/`Category`-style
aggregate with invariants of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.shared.ids import TenantId


@dataclass(frozen=True)
class OutboxEvent:
    id: UUID
    tenant_id: TenantId
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
    published_at: datetime | None


class OutboxEventRepository(Protocol):
    async def add(
        self, tenant_id: TenantId, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> UUID: ...

    async def list_unpublished(self, tenant_id: TenantId, *, limit: int) -> list[OutboxEvent]:
        """Oldest first — the order a relay should publish in, to preserve
        the sequence events actually happened in."""
        ...

    async def mark_published(
        self, tenant_id: TenantId, event_id: UUID, *, now: datetime
    ) -> None: ...
