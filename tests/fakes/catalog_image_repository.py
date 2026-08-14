from __future__ import annotations

from datetime import datetime

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.shared.ids import (
    CatalogImageId,
    CatalogImageSlotId,
    ProductId,
    ProductVariantId,
    TenantId,
)
from app.shared.pagination import Cursor
from tests.fakes.product_variant_repository import InMemoryProductVariantRepository


class InMemoryCatalogImageRepository:
    def __init__(self, product_variants: InMemoryProductVariantRepository) -> None:
        self._rows: dict[tuple[TenantId, CatalogImageId], CatalogImage] = {}
        self._product_variants = product_variants

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

    async def list_page(
        self,
        tenant_id: TenantId,
        *,
        status: CatalogImageStatus | None,
        product_id: ProductId | None,
        after: Cursor | None,
        limit: int,
    ) -> list[CatalogImage]:
        variant_ids: set[ProductVariantId] | None = None
        if product_id is not None:
            variants = await self._product_variants.list_for_product(tenant_id, product_id)
            variant_ids = {v.id for v in variants}

        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id
            and row.superseded_by is None
            and (status is None or row.status == status)
            and (variant_ids is None or row.variant_id in variant_ids)
        ]
        matches.sort(key=lambda row: (row.created_at, row.id))
        if after is not None:
            after_key = (datetime.fromisoformat(after.sort_key), after.id)
            matches = [row for row in matches if (row.created_at, row.id) > after_key]
        return matches[:limit]
