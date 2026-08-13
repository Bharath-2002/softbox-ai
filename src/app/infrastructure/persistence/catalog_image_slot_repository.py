"""Implements
``app.services.ports.catalog_image_slot_repository.CatalogImageSlotRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.image_slots import CatalogImageSlot
from app.infrastructure.persistence.mapping import catalog_image_slots_table
from app.shared.ids import CatalogImageSlotId, CategoryId, TenantId


class SqlCatalogImageSlotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, slot_id: CatalogImageSlotId
    ) -> CatalogImageSlot | None:
        stmt = select(CatalogImageSlot).where(
            catalog_image_slots_table.c.tenant_id == tenant_id,
            catalog_image_slots_table.c.id == slot_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, slot: CatalogImageSlot) -> None:
        self._session.add(slot)
        await self._session.flush()

    async def update(self, slot: CatalogImageSlot) -> None:
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CatalogImageSlot]:
        stmt = (
            select(CatalogImageSlot)
            .where(
                catalog_image_slots_table.c.tenant_id == tenant_id,
                catalog_image_slots_table.c.category_id == category_id,
            )
            .order_by(catalog_image_slots_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[CatalogImageSlot]:
        if not category_ids:
            return []
        stmt = (
            select(CatalogImageSlot)
            .where(
                catalog_image_slots_table.c.tenant_id == tenant_id,
                catalog_image_slots_table.c.category_id.in_(category_ids),
            )
            .order_by(catalog_image_slots_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())
