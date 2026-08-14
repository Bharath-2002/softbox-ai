from __future__ import annotations

import pytest

from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import (
    new_asset_id,
    new_input_image_slot_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)


def _image() -> ProductInputImage:
    return ProductInputImage.create(
        new_tenant_id(),
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=utcnow(),
    )


def test_a_new_input_image_starts_captured_with_no_variant_and_no_derivative() -> None:
    image = _image()

    assert image.status == InputImageStatus.CAPTURED
    assert image.variant_id is None
    assert image.normalised_asset_id is None
    assert image.rejection_reason is None


def test_a_validated_image_can_be_marked_ready_skipping_normalising() -> None:
    image = _image()
    image.start_validating(now=utcnow())

    image.mark_ready(now=utcnow())

    assert image.status == InputImageStatus.READY


def test_a_validated_image_can_be_rejected_with_a_reason() -> None:
    image = _image()
    image.start_validating(now=utcnow())

    image.mark_rejected(reason="too blurry - retake in better light", now=utcnow())

    assert image.status == InputImageStatus.REJECTED
    assert image.rejection_reason == "too blurry - retake in better light"


def test_a_captured_image_cannot_be_marked_ready_directly() -> None:
    image = _image()

    with pytest.raises(ValidationError, match="Cannot mark ready"):
        image.mark_ready(now=utcnow())


def test_a_rejected_image_cannot_be_validated_again() -> None:
    image = _image()
    image.start_validating(now=utcnow())
    image.mark_rejected(reason="too dark", now=utcnow())

    with pytest.raises(ValidationError, match="Cannot start validation"):
        image.start_validating(now=utcnow())
