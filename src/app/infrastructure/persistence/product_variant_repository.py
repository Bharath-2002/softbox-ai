"""Implements
``app.services.ports.product_variant_repository.ProductVariantRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.product_variant import ProductVariant
from app.infrastructure.persistence.mapping import product_variants_table
from app.shared.ids import ProductId, ProductVariantId, TenantId


class SqlProductVariantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, variant_id: ProductVariantId) -> ProductVariant | None:
        stmt = select(ProductVariant).where(
            product_variants_table.c.tenant_id == tenant_id,
            product_variants_table.c.id == variant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, variant: ProductVariant) -> None:
        self._session.add(variant)
        await self._session.flush()

    async def update(self, variant: ProductVariant) -> None:
        await self._session.flush()

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductVariant]:
        stmt = (
            select(ProductVariant)
            .where(
                product_variants_table.c.tenant_id == tenant_id,
                product_variants_table.c.product_id == product_id,
            )
            .order_by(product_variants_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())
