"""Product input image storage (D12, §6.1).

``list_for_product`` returns every row for the product, both product-level
(``variant_id`` NULL) and every variant's own rows — the shape
``services.input_image_resolution.resolve_input_image`` expects, since the
D12 resolution rule needs both to pick the right one for a given variant.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.product_input_image import ProductInputImage
from app.shared.ids import ProductId, ProductInputImageId, TenantId


class ProductInputImageRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, image_id: ProductInputImageId
    ) -> ProductInputImage | None: ...

    async def add(self, image: ProductInputImage) -> None: ...

    async def update(self, image: ProductInputImage) -> None: ...

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductInputImage]: ...
