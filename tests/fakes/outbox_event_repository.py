from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.services.ports.outbox_event_repository import OutboxEvent
from app.shared.ids import TenantId


class InMemoryOutboxEventRepository:
    def __init__(self) -> None:
        self._rows: dict[UUID, OutboxEvent] = {}

    async def add(
        self, tenant_id: TenantId, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> UUID:
        event_id = uuid4()
        self._rows[event_id] = OutboxEvent(
            id=event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            created_at=now,
            published_at=None,
        )
        return event_id

    async def list_unpublished(self, tenant_id: TenantId, *, limit: int) -> list[OutboxEvent]:
        matches = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.published_at is None
        ]
        matches.sort(key=lambda row: row.created_at)
        return matches[:limit]

    async def mark_published(self, tenant_id: TenantId, event_id: UUID, *, now: datetime) -> None:
        row = self._rows.get(event_id)
        if row is not None and row.tenant_id == tenant_id:
            self._rows[event_id] = replace(row, published_at=now)
