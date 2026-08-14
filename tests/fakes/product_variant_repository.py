from __future__ import annotations

from app.entities.product_variant import ProductVariant
from app.shared.ids import ProductId, ProductVariantId, TenantId


class InMemoryProductVariantRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, ProductVariantId], ProductVariant] = {}

    async def get(self, tenant_id: TenantId, variant_id: ProductVariantId) -> ProductVariant | None:
        return self._rows.get((tenant_id, variant_id))

    async def add(self, variant: ProductVariant) -> None:
        self._rows[(variant.tenant_id, variant.id)] = variant

    async def update(self, variant: ProductVariant) -> None:
        self._rows[(variant.tenant_id, variant.id)] = variant

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductVariant]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.product_id == product_id
        ]
        return sorted(matches, key=lambda row: row.position)
