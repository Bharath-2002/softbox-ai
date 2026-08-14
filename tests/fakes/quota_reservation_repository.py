from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime

from app.services.ports.quota_reservation_repository import QuotaReservation
from app.shared.ids import TenantId


class InMemoryQuotaReservationRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, str, str], QuotaReservation] = {}

    async def ensure_period(
        self, tenant_id: TenantId, *, period: str, metric: str, limit_value: int, now: datetime
    ) -> None:
        key = (tenant_id, period, metric)
        if key in self._rows:
            return
        self._rows[key] = QuotaReservation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            period=period,
            metric=metric,
            limit_value=limit_value,
            reserved=0,
            committed=0,
        )

    async def reserve(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> bool:
        row = self._rows.get((tenant_id, period, metric))
        if row is None or row.limit_value - row.reserved < quantity:
            return False
        self._rows[(tenant_id, period, metric)] = replace(row, reserved=row.reserved + quantity)
        return True

    async def commit(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        row = self._rows.get((tenant_id, period, metric))
        if row is not None:
            self._rows[(tenant_id, period, metric)] = replace(
                row, committed=row.committed + quantity
            )

    async def release(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        row = self._rows.get((tenant_id, period, metric))
        if row is not None:
            self._rows[(tenant_id, period, metric)] = replace(row, reserved=row.reserved - quantity)

    async def get(
        self, tenant_id: TenantId, *, period: str, metric: str
    ) -> QuotaReservation | None:
        return self._rows.get((tenant_id, period, metric))
