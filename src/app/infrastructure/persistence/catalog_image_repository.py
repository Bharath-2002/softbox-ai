"""Implements
``app.services.ports.catalog_image_repository.CatalogImageRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.catalog_image import CatalogImage
from app.infrastructure.persistence.mapping import catalog_images_table
from app.shared.ids import CatalogImageId, CatalogImageSlotId, ProductVariantId, TenantId


class SqlCatalogImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, image_id: CatalogImageId) -> CatalogImage | None:
        stmt = select(CatalogImage).where(
            catalog_images_table.c.tenant_id == tenant_id,
            catalog_images_table.c.id == image_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_live(
        self,
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        catalog_image_slot_id: CatalogImageSlotId,
    ) -> CatalogImage | None:
        stmt = select(CatalogImage).where(
            catalog_images_table.c.tenant_id == tenant_id,
            catalog_images_table.c.variant_id == variant_id,
            catalog_images_table.c.catalog_image_slot_id == catalog_image_slot_id,
            catalog_images_table.c.superseded_by.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, image: CatalogImage) -> None:
        self._session.add(image)
        await self._session.flush()

    async def update(self, image: CatalogImage) -> None:
        await self._session.flush()

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[CatalogImage]:
        stmt = select(CatalogImage).where(
            catalog_images_table.c.tenant_id == tenant_id,
            catalog_images_table.c.variant_id == variant_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
