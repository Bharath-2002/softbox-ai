"""Implements ``app.services.ports.product_repository.ProductRepository``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.product import Product
from app.infrastructure.persistence.mapping import products_table
from app.shared.ids import CategoryId, ProductId, TenantId
from app.shared.pagination import Cursor


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

    async def list_page(
        self,
        tenant_id: TenantId,
        category_id: CategoryId | None,
        *,
        after: Cursor | None,
        limit: int,
    ) -> list[Product]:
        stmt = select(Product).where(products_table.c.tenant_id == tenant_id)
        if category_id is not None:
            stmt = stmt.where(products_table.c.category_id == category_id)
        if after is not None:
            stmt = stmt.where(
                tuple_(products_table.c.created_at, products_table.c.id)
                > (datetime.fromisoformat(after.sort_key), after.id)
            )
        stmt = stmt.order_by(products_table.c.created_at, products_table.c.id).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())
