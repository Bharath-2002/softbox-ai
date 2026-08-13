"""Implements ``app.services.ports.variant_axis_repository.VariantAxisRepository``.

Filters use ``variant_axes_table.c.*``, not the mapped class's own
attributes — see ``user_repository.py`` for why.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.variant_axis import VariantAxis
from app.infrastructure.persistence.mapping import variant_axes_table
from app.shared.ids import CategoryId, TenantId, VariantAxisId


class SqlVariantAxisRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, axis_id: VariantAxisId) -> VariantAxis | None:
        stmt = select(VariantAxis).where(
            variant_axes_table.c.tenant_id == tenant_id, variant_axes_table.c.id == axis_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, axis: VariantAxis) -> None:
        self._session.add(axis)
        await self._session.flush()

    async def update(self, axis: VariantAxis) -> None:
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[VariantAxis]:
        stmt = (
            select(VariantAxis)
            .where(
                variant_axes_table.c.tenant_id == tenant_id,
                variant_axes_table.c.category_id == category_id,
            )
            .order_by(variant_axes_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[VariantAxis]:
        if not category_ids:
            return []
        stmt = (
            select(VariantAxis)
            .where(
                variant_axes_table.c.tenant_id == tenant_id,
                variant_axes_table.c.category_id.in_(category_ids),
            )
            .order_by(variant_axes_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())
