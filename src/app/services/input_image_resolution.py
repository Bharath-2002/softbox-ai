"""D12's resolution rule: for input slot S on variant V, use V's image for S
if present, else the product's image for S. Pure — operates on an
already-fetched list (``ProductInputImageRepository.list_for_product``, which
returns every row for the product regardless of ``variant_id``), the same
shape as ``template_placeholder_validator``/``prompt_rendering``.
"""

from __future__ import annotations

from app.entities.product_input_image import ProductInputImage
from app.shared.ids import InputImageSlotId, ProductVariantId


def resolve_input_image(
    images: list[ProductInputImage],
    *,
    variant_id: ProductVariantId | None,
    input_image_slot_id: InputImageSlotId,
) -> ProductInputImage | None:
    if variant_id is not None:
        for image in images:
            if image.variant_id == variant_id and image.input_image_slot_id == input_image_slot_id:
                return image

    for image in images:
        if image.variant_id is None and image.input_image_slot_id == input_image_slot_id:
            return image

    return None
