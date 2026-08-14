"""Port for `catalog_images` (D18) — the mutable current-state row per
(variant, catalog slot). `update` exists (unlike `GenerationItemRepository`)
because this row is revised over its QC/approval lifecycle and, critically,
`mark_superseded` on the *existing* row is one half of the regeneration
transaction. `get_live` finds that existing row — the one with
`superseded_by IS NULL` for a given (variant, slot), i.e. the row the
partial unique index currently protects.

`list_page` (M6) is the approval queue's discovery query, cursor-paginated
(CLAUDE.md §9) the same way `ProductRepository.list_page` is — ordered
`(created_at, id)` ascending, no trimming/cursor-encoding of its own. It
**always** excludes superseded rows (`superseded_by IS NOT NULL`):
regeneration can supersede a `pending_approval` image before anyone ever
acts on it (a new "Save & Generate" doesn't wait on an old one's approval
state), and a superseded row is no longer anything a human should be
approving or rejecting — there is no caller anywhere that wants to see
those, so this is not a filter parameter, it is the query's own definition
of "queue."
"""

from __future__ import annotations

from typing import Protocol

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.shared.ids import (
    CatalogImageId,
    CatalogImageSlotId,
    ProductId,
    ProductVariantId,
    TenantId,
)
from app.shared.pagination import Cursor


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

    async def list_page(
        self,
        tenant_id: TenantId,
        *,
        status: CatalogImageStatus | None,
        product_id: ProductId | None,
        after: Cursor | None,
        limit: int,
    ) -> list[CatalogImage]:
        """Live (non-superseded) images, optionally filtered to one status
        and/or one product (joining through `product_variants`).
        `status=None` lists every live status — used for a product's "all
        images" bulk-approve view, not the ordinary queue."""
        ...
