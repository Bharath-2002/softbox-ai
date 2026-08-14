"""Binds an already-uploaded, already-verified `Asset` (from
`VerifyAndRegisterUpload`) to a product (or one of its variants) as a
`ProductInputImage`, `captured` (§6.1) — the missing link between the
upload pipeline (M3) and the validation pipeline
(`InputImageValidationAgent`, M4): nothing else creates a
`ProductInputImage` row today.

`input_image_slot_id` is checked against the product's **pinned** spec
snapshot (`product.spec_version_id`), the same D15 discipline every other
M4 use case follows — an unresolvable slot id would silently produce a row
`resolve_input_image` can never be asked for by the D12 resolution rule
(nothing has a reason to request a slot that isn't in the spec), so this is
a validation failure, not a permissive no-op. The asset must already be a
verified `AssetKind.INPUT` row belonging to this tenant — this use case
does no bytes-level work of its own, only wiring.

**Recapturing the same slot is not deduplicated or superseded.** Calling
this twice for the same `(product_id, variant_id, input_image_slot_id)`
creates two rows; `resolve_input_image` returns whichever `list_for_product`
happens to return first, which is an existing property of that function,
not something introduced here. A "replace the previous capture for this
slot" use case is a real gap, left open rather than guessed at, since
nothing in the checklist specifies the intended UX for a retake.
"""

from __future__ import annotations

from app.entities.asset import AssetKind
from app.entities.product_input_image import ProductInputImage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import AssetId, InputImageSlotId, ProductId, ProductVariantId, TenantId, UserId


class CaptureProductInputImage:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        product_id: ProductId,
        input_image_slot_id: InputImageSlotId,
        asset_id: AssetId,
        created_by: UserId,
        variant_id: ProductVariantId | None = None,
    ) -> ProductInputImage:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            if variant_id is not None:
                variant = await uow.product_variants.get(tenant_id, variant_id)
                if variant is None or variant.product_id != product_id:
                    raise NotFoundError("Product variant not found.")

            asset = await uow.assets.get(tenant_id, asset_id)
            if asset is None:
                raise NotFoundError("Asset not found.")
            if asset.kind is not AssetKind.INPUT:
                raise ValidationError(f"Asset kind {asset.kind.value!r} is not an input photo.")

            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )
            slot_ids = {slot["id"] for slot in spec_version.snapshot.get("input_image_slots", [])}
            if str(input_image_slot_id) not in slot_ids:
                raise ValidationError("Input image slot is not part of this product's spec.")

            now = self._clock.now()
            image = ProductInputImage.create(
                tenant_id,
                product_id,
                input_image_slot_id=input_image_slot_id,
                asset_id=asset_id,
                created_by=created_by,
                now=now,
                variant_id=variant_id,
            )
            await uow.product_input_images.add(image)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=created_by,
                action="product_input_image.captured",
                subject_type="product_input_image",
                subject_id=image.id,
                before=None,
                after={"product_id": str(product_id), "asset_id": str(asset_id)},
                now=now,
            )

            return image
