"""Implements
``app.services.ports.input_image_slot_repository.InputImageSlotRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.image_slots import InputImageSlot
from app.infrastructure.persistence.mapping import input_image_slots_table
from app.shared.ids import CategoryId, InputImageSlotId, TenantId


class SqlInputImageSlotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, slot_id: InputImageSlotId) -> InputImageSlot | None:
        stmt = select(InputImageSlot).where(
            input_image_slots_table.c.tenant_id == tenant_id,
            input_image_slots_table.c.id == slot_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, slot: InputImageSlot) -> None:
        self._session.add(slot)
        await self._session.flush()

    async def update(self, slot: InputImageSlot) -> None:
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[InputImageSlot]:
        stmt = (
            select(InputImageSlot)
            .where(
                input_image_slots_table.c.tenant_id == tenant_id,
                input_image_slots_table.c.category_id == category_id,
            )
            .order_by(input_image_slots_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[InputImageSlot]:
        if not category_ids:
            return []
        stmt = (
            select(InputImageSlot)
            .where(
                input_image_slots_table.c.tenant_id == tenant_id,
                input_image_slots_table.c.category_id.in_(category_ids),
            )
            .order_by(input_image_slots_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())
