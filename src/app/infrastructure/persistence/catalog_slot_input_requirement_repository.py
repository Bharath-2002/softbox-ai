"""Implements
``app.services.ports.catalog_slot_input_requirement_repository.CatalogSlotInputRequirementRepository``.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.infrastructure.persistence.mapping import catalog_slot_input_requirements_table
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId

_t = catalog_slot_input_requirements_table


class SqlCatalogSlotInputRequirementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> CatalogSlotInputRequirement | None:
        stmt = select(CatalogSlotInputRequirement).where(
            _t.c.tenant_id == tenant_id,
            _t.c.catalog_image_slot_id == catalog_image_slot_id,
            _t.c.input_image_slot_id == input_image_slot_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, requirement: CatalogSlotInputRequirement) -> None:
        self._session.add(requirement)
        await self._session.flush()

    async def update(self, requirement: CatalogSlotInputRequirement) -> None:
        await self._session.flush()

    async def remove(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> None:
        stmt = delete(_t).where(
            _t.c.tenant_id == tenant_id,
            _t.c.catalog_image_slot_id == catalog_image_slot_id,
            _t.c.input_image_slot_id == input_image_slot_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        stmt = (
            select(CatalogSlotInputRequirement)
            .where(
                _t.c.tenant_id == tenant_id,
                _t.c.catalog_image_slot_id == catalog_image_slot_id,
            )
            .order_by(_t.c.prompt_position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_input_slot(
        self, tenant_id: TenantId, input_image_slot_id: InputImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        stmt = select(CatalogSlotInputRequirement).where(
            _t.c.tenant_id == tenant_id,
            _t.c.input_image_slot_id == input_image_slot_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
