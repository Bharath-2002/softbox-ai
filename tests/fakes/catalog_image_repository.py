from __future__ import annotations

from app.entities.catalog_image import CatalogImage
from app.shared.ids import CatalogImageId, CatalogImageSlotId, ProductVariantId, TenantId


class InMemoryCatalogImageRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, CatalogImageId], CatalogImage] = {}

    async def get(self, tenant_id: TenantId, image_id: CatalogImageId) -> CatalogImage | None:
        return self._rows.get((tenant_id, image_id))

    async def get_live(
        self,
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        catalog_image_slot_id: CatalogImageSlotId,
    ) -> CatalogImage | None:
        for (tid, _), row in self._rows.items():
            if (
                tid == tenant_id
                and row.variant_id == variant_id
                and row.catalog_image_slot_id == catalog_image_slot_id
                and row.superseded_by is None
            ):
                return row
        return None

    async def add(self, image: CatalogImage) -> None:
        self._rows[(image.tenant_id, image.id)] = image

    async def update(self, image: CatalogImage) -> None:
        self._rows[(image.tenant_id, image.id)] = image

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[CatalogImage]:
        return [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.variant_id == variant_id
        ]
