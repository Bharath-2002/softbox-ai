"""Implements
``app.services.ports.catalog_image_repository.CatalogImageRepository``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.infrastructure.persistence.mapping import catalog_images_table, product_variants_table
from app.shared.ids import (
    CatalogImageId,
    CatalogImageSlotId,
    ProductId,
    ProductVariantId,
    TenantId,
)
from app.shared.pagination import Cursor


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

    async def list_page(
        self,
        tenant_id: TenantId,
        *,
        status: CatalogImageStatus | None,
        product_id: ProductId | None,
        after: Cursor | None,
        limit: int,
    ) -> list[CatalogImage]:
        stmt = select(CatalogImage).where(
            catalog_images_table.c.tenant_id == tenant_id,
            catalog_images_table.c.superseded_by.is_(None),
        )
        if status is not None:
            stmt = stmt.where(catalog_images_table.c.status == status.value)
        if product_id is not None:
            stmt = stmt.join(
                product_variants_table,
                (product_variants_table.c.id == catalog_images_table.c.variant_id)
                & (product_variants_table.c.tenant_id == tenant_id),
            ).where(product_variants_table.c.product_id == product_id)
        if after is not None:
            stmt = stmt.where(
                tuple_(catalog_images_table.c.created_at, catalog_images_table.c.id)
                > (datetime.fromisoformat(after.sort_key), after.id)
            )
        stmt = stmt.order_by(catalog_images_table.c.created_at, catalog_images_table.c.id).limit(
            limit
        )
        return list((await self._session.execute(stmt)).scalars().all())
