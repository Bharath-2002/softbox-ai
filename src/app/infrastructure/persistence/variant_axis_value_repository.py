"""Implements
``app.services.ports.variant_axis_value_repository.VariantAxisValueRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.variant_axis import VariantAxisValue
from app.infrastructure.persistence.mapping import variant_axis_values_table
from app.shared.ids import TenantId, VariantAxisId, VariantAxisValueId


class SqlVariantAxisValueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, value_id: VariantAxisValueId
    ) -> VariantAxisValue | None:
        stmt = select(VariantAxisValue).where(
            variant_axis_values_table.c.tenant_id == tenant_id,
            variant_axis_values_table.c.id == value_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, value: VariantAxisValue) -> None:
        self._session.add(value)
        await self._session.flush()

    async def update(self, value: VariantAxisValue) -> None:
        await self._session.flush()

    async def list_for_axis(
        self, tenant_id: TenantId, axis_id: VariantAxisId
    ) -> list[VariantAxisValue]:
        stmt = select(VariantAxisValue).where(
            variant_axis_values_table.c.tenant_id == tenant_id,
            variant_axis_values_table.c.axis_id == axis_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
