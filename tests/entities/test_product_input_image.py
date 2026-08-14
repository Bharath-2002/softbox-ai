from __future__ import annotations

from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.shared.clock import utcnow
from app.shared.ids import (
    new_asset_id,
    new_input_image_slot_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)


def test_a_new_input_image_starts_captured_with_no_variant_and_no_derivative() -> None:
    image = ProductInputImage.create(
        new_tenant_id(),
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=utcnow(),
    )

    assert image.status == InputImageStatus.CAPTURED
    assert image.variant_id is None
    assert image.normalised_asset_id is None
    assert image.rejection_reason is None
