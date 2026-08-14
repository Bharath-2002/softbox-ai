"""Implements
``app.services.ports.outbox_event_repository.OutboxEventRepository``.

Core queries against ``outbox_events_table`` directly — no rich entity,
same shape as ``SqlIdempotencyRepository``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import outbox_events_table
from app.services.ports.outbox_event_repository import OutboxEvent
from app.shared.ids import TenantId


class SqlOutboxEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, tenant_id: TenantId, *, event_type: str, payload: dict[str, Any], now: datetime
    ) -> UUID:
        event_id = uuid.uuid4()
        stmt = insert(outbox_events_table).values(
            id=event_id,
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            created_at=now,
            published_at=None,
        )
        await self._session.execute(stmt)
        await self._session.flush()
        return event_id

    async def list_unpublished(self, tenant_id: TenantId, *, limit: int) -> list[OutboxEvent]:
        stmt = (
            select(outbox_events_table)
            .where(
                outbox_events_table.c.tenant_id == tenant_id,
                outbox_events_table.c.published_at.is_(None),
            )
            .order_by(outbox_events_table.c.created_at)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            OutboxEvent(
                id=row.id,
                tenant_id=row.tenant_id,
                event_type=row.event_type,
                payload=row.payload,
                created_at=row.created_at,
                published_at=row.published_at,
            )
            for row in rows
        ]

    async def mark_published(self, tenant_id: TenantId, event_id: UUID, *, now: datetime) -> None:
        stmt = (
            update(outbox_events_table)
            .where(
                outbox_events_table.c.tenant_id == tenant_id,
                outbox_events_table.c.id == event_id,
            )
            .values(published_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()
