"""Implements
``app.services.ports.quota_reservation_repository.QuotaReservationRepository``.

Core queries against ``quota_reservations_table`` directly — no rich
entity, same shape as ``SqlTaskQueue``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import quota_reservations_table
from app.services.ports.quota_reservation_repository import QuotaReservation
from app.shared.ids import TenantId


def _to_reservation(row: Any) -> QuotaReservation:
    return QuotaReservation(
        id=row.id,
        tenant_id=row.tenant_id,
        period=row.period,
        metric=row.metric,
        limit_value=row.limit_value,
        reserved=row.reserved,
        committed=row.committed,
    )


class SqlQuotaReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_period(
        self, tenant_id: TenantId, *, period: str, metric: str, limit_value: int, now: datetime
    ) -> None:
        stmt = (
            pg_insert(quota_reservations_table)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                period=period,
                metric=metric,
                limit_value=limit_value,
                reserved=0,
                committed=0,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    quota_reservations_table.c.tenant_id,
                    quota_reservations_table.c.period,
                    quota_reservations_table.c.metric,
                ]
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def reserve(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> bool:
        stmt = (
            update(quota_reservations_table)
            .where(
                quota_reservations_table.c.tenant_id == tenant_id,
                quota_reservations_table.c.period == period,
                quota_reservations_table.c.metric == metric,
                quota_reservations_table.c.limit_value - quota_reservations_table.c.reserved
                >= quantity,
            )
            .values(reserved=quota_reservations_table.c.reserved + quantity, updated_at=now)
            .returning(quota_reservations_table.c.id)
        )
        result = (await self._session.execute(stmt)).first()
        await self._session.flush()
        return result is not None

    async def commit(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        stmt = (
            update(quota_reservations_table)
            .where(
                quota_reservations_table.c.tenant_id == tenant_id,
                quota_reservations_table.c.period == period,
                quota_reservations_table.c.metric == metric,
            )
            .values(committed=quota_reservations_table.c.committed + quantity, updated_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def release(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        stmt = (
            update(quota_reservations_table)
            .where(
                quota_reservations_table.c.tenant_id == tenant_id,
                quota_reservations_table.c.period == period,
                quota_reservations_table.c.metric == metric,
            )
            .values(reserved=quota_reservations_table.c.reserved - quantity, updated_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get(
        self, tenant_id: TenantId, *, period: str, metric: str
    ) -> QuotaReservation | None:
        stmt = select(quota_reservations_table).where(
            quota_reservations_table.c.tenant_id == tenant_id,
            quota_reservations_table.c.period == period,
            quota_reservations_table.c.metric == metric,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        return _to_reservation(row) if row is not None else None
