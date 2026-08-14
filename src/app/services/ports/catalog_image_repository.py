"""Port for `catalog_images` (D18) — the mutable current-state row per
(variant, catalog slot). `update` exists (unlike `GenerationItemRepository`)
because this row is revised over its QC/approval lifecycle and, critically,
`mark_superseded` on the *existing* row is one half of the regeneration
transaction. `get_live` finds that existing row — the one with
`superseded_by IS NULL` for a given (variant, slot), i.e. the row the
partial unique index currently protects.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.catalog_image import CatalogImage
from app.shared.ids import CatalogImageId, CatalogImageSlotId, ProductVariantId, TenantId


class CatalogImageRepository(Protocol):
    async def get(self, tenant_id: TenantId, image_id: CatalogImageId) -> CatalogImage | None: ...

    async def get_live(
        self,
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        catalog_image_slot_id: CatalogImageSlotId,
    ) -> CatalogImage | None:
        """The row for this (variant, slot) with `superseded_by IS NULL`, if
        any — at most one can exist, enforced by the partial unique index."""
        ...

    async def add(self, image: CatalogImage) -> None: ...

    async def update(self, image: CatalogImage) -> None: ...

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[CatalogImage]: ...
