"""Implements ``app.services.ports.product_repository.ProductRepository``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.product import Product
from app.infrastructure.persistence.mapping import products_table
from app.shared.ids import CategoryId, ProductId, TenantId


class SqlProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, product_id: ProductId) -> Product | None:
        stmt = select(Product).where(
            products_table.c.tenant_id == tenant_id, products_table.c.id == product_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, product: Product) -> None:
        self._session.add(product)
        await self._session.flush()

    async def update(self, product: Product) -> None:
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[Product]:
        stmt = (
            select(Product)
            .where(
                products_table.c.tenant_id == tenant_id,
                products_table.c.category_id == category_id,
            )
            .order_by(products_table.c.created_at)
        )
        return list((await self._session.execute(stmt)).scalars().all())
