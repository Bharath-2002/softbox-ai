"""Product storage (D11, D12). Same shape as ``CatalogTemplateRepository``.

No ``get_by_sku``/``get_by_title`` lookup yet — ``sku``/``title`` are
promoted, nullable columns (a category need not declare either semantic
role), so a uniqueness-backed lookup on either is a later use case's
concern, not this port's, until one actually needs it.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.product import Product
from app.shared.ids import CategoryId, ProductId, TenantId


class ProductRepository(Protocol):
    async def get(self, tenant_id: TenantId, product_id: ProductId) -> Product | None: ...

    async def add(self, product: Product) -> None: ...

    async def update(self, product: Product) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[Product]: ...
