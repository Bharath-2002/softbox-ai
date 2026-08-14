"""Product variant storage (D12). Same shape as ``ProductRepository``."""

from __future__ import annotations

from typing import Protocol

from app.entities.product_variant import ProductVariant
from app.shared.ids import ProductId, ProductVariantId, TenantId


class ProductVariantRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> ProductVariant | None: ...

    async def add(self, variant: ProductVariant) -> None: ...

    async def update(self, variant: ProductVariant) -> None: ...

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductVariant]: ...
