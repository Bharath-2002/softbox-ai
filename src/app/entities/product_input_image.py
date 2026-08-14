"""A captured input photo bound to a product (D12, §6.1). `variant_id` is
nullable — NULL means the image is shared across every variant of the
product; a non-null value means it belongs to one specific variant (A6's
"photographed" colour-variant path). The D12 resolution rule (*for input
slot S on variant V, use V's image for S if present, else the product's
image for S*) lives in `services.input_image_resolution`, not here — this
entity only carries the row shape.

`asset_id` is the original upload, always retained (§6.1: "the original is
always retained"). `normalised_asset_id` is nullable and set once the
normalising step produces a derivative asset — never in place of `asset_id`.

`status` runs the §6.1 state machine: `captured -> validating -> normalising
-> ready / rejected`. Only `create` (-> `captured`) exists as an entity
method so far, matching every other new entity this milestone — the
`validating` step lands with a real Pillow-based use case; `normalising`
needs an `ImageNormalisation` port with no adapter (background removal,
colour calibration, perspective correction and de-creasing all need
`rembg`/OpenCV or a hosted service — CLAUDE.md says stop and ask before
adding a new third-party dependency, so that adapter does not exist yet, the
same posture `VisionAnalysis` takes on the vision side).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.ids import (
    AssetId,
    InputImageSlotId,
    ProductId,
    ProductInputImageId,
    ProductVariantId,
    TenantId,
    UserId,
    new_product_input_image_id,
)


class InputImageStatus(StrEnum):
    CAPTURED = "captured"
    VALIDATING = "validating"
    NORMALISING = "normalising"
    READY = "ready"
    REJECTED = "rejected"


@dataclass
class ProductInputImage:
    id: ProductInputImageId
    tenant_id: TenantId
    product_id: ProductId
    variant_id: ProductVariantId | None
    input_image_slot_id: InputImageSlotId
    asset_id: AssetId
    normalised_asset_id: AssetId | None
    status: InputImageStatus
    rejection_reason: str | None
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        product_id: ProductId,
        *,
        input_image_slot_id: InputImageSlotId,
        asset_id: AssetId,
        created_by: UserId,
        now: datetime,
        variant_id: ProductVariantId | None = None,
    ) -> ProductInputImage:
        return ProductInputImage(
            id=new_product_input_image_id(),
            tenant_id=tenant_id,
            product_id=product_id,
            variant_id=variant_id,
            input_image_slot_id=input_image_slot_id,
            asset_id=asset_id,
            normalised_asset_id=None,
            status=InputImageStatus.CAPTURED,
            rejection_reason=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
