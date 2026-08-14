"""Implements
``app.services.ports.catalog_template_repository.CatalogTemplateRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.catalog_template import CatalogTemplate
from app.infrastructure.persistence.mapping import catalog_templates_table
from app.shared.ids import CatalogImageSlotId, CatalogTemplateId, TenantId


class SqlCatalogTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, template_id: CatalogTemplateId
    ) -> CatalogTemplate | None:
        stmt = select(CatalogTemplate).where(
            catalog_templates_table.c.tenant_id == tenant_id,
            catalog_templates_table.c.id == template_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, template: CatalogTemplate) -> None:
        self._session.add(template)
        await self._session.flush()

    async def update(self, template: CatalogTemplate) -> None:
        await self._session.flush()

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogTemplate]:
        stmt = (
            select(CatalogTemplate)
            .where(
                catalog_templates_table.c.tenant_id == tenant_id,
                catalog_templates_table.c.catalog_image_slot_id == catalog_image_slot_id,
            )
            .order_by(catalog_templates_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_latest_version(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId, name: str
    ) -> CatalogTemplate | None:
        stmt = (
            select(CatalogTemplate)
            .where(
                catalog_templates_table.c.tenant_id == tenant_id,
                catalog_templates_table.c.catalog_image_slot_id == catalog_image_slot_id,
                catalog_templates_table.c.name == name,
            )
            .order_by(catalog_templates_table.c.version.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
