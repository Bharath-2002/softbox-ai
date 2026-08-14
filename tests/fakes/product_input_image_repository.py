from __future__ import annotations

from app.entities.product_input_image import ProductInputImage
from app.shared.ids import ProductId, ProductInputImageId, TenantId


class InMemoryProductInputImageRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, ProductInputImageId], ProductInputImage] = {}

    async def get(
        self, tenant_id: TenantId, image_id: ProductInputImageId
    ) -> ProductInputImage | None:
        return self._rows.get((tenant_id, image_id))

    async def add(self, image: ProductInputImage) -> None:
        self._rows[(image.tenant_id, image.id)] = image

    async def update(self, image: ProductInputImage) -> None:
        self._rows[(image.tenant_id, image.id)] = image

    async def list_for_product(
        self, tenant_id: TenantId, product_id: ProductId
    ) -> list[ProductInputImage]:
        return [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.product_id == product_id
        ]
