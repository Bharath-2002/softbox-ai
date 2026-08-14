"""Implements
``app.services.ports.product_input_image_repository.ProductInputImageRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.product_input_image import ProductInputImage
from app.infrastructure.persistence.mapping import product_input_images_table
from app.shared.ids import ProductId, ProductInputImageId, TenantId


class SqlProductInputImageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, image_id: ProductInputImageId
    ) -> ProductInputImage | None:
        stmt = select(ProductInputImage).where(
            product_input_images_table.c.tenant_id == tenant_id,
            product_input_images_table.c.id == image_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, image: ProductInputImage) -> None:
        self._session.add(image)
        await self._session.flush()

    async def update(self, image: ProductInputImage) -> None:
        await self._session.flush()

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductInputImage]:
        stmt = select(ProductInputImage).where(
            product_input_images_table.c.tenant_id == tenant_id,
            product_input_images_table.c.product_id == product_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
