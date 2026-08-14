from __future__ import annotations

from app.entities.product import Product
from app.shared.ids import CategoryId, ProductId, TenantId


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
