from __future__ import annotations

from datetime import datetime

from app.entities.product import Product, ProductStatus
from app.shared.ids import CategoryId, ProductId, TenantId
from app.shared.pagination import Cursor


class InMemoryProductRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, ProductId], Product] = {}

    async def get(self, tenant_id: TenantId, product_id: ProductId) -> Product | None:
        return self._rows.get((tenant_id, product_id))

    async def add(self, product: Product) -> None:
        self._rows[(product.tenant_id, product.id)] = product

    async def update(self, product: Product) -> None:
        self._rows[(product.tenant_id, product.id)] = product

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[Product]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.created_at)

    async def list_page(
        self,
        tenant_id: TenantId,
        category_id: CategoryId | None,
        *,
        after: Cursor | None,
        limit: int,
    ) -> list[Product]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and (category_id is None or row.category_id == category_id)
        ]
        matches.sort(key=lambda row: (row.created_at, row.id))
        if after is not None:
            after_key = (datetime.fromisoformat(after.sort_key), after.id)
            matches = [row for row in matches if (row.created_at, row.id) > after_key]
        return matches[:limit]

    async def list_published_page(
        self,
        tenant_id: TenantId,
        category_id: CategoryId | None,
        *,
        after: Cursor | None,
        limit: int,
    ) -> list[Product]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id
            and row.status is ProductStatus.PUBLISHED
            and (category_id is None or row.category_id == category_id)
        ]
        matches.sort(key=lambda row: (row.created_at, row.id))
        if after is not None:
            after_key = (datetime.fromisoformat(after.sort_key), after.id)
            matches = [row for row in matches if (row.created_at, row.id) > after_key]
        return matches[:limit]
