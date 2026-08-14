"""D12's resolution rule, both directions (M4 Gate)."""

from __future__ import annotations

from app.entities.product_input_image import ProductInputImage
from app.services.input_image_resolution import resolve_input_image
from app.shared.clock import utcnow
from app.shared.ids import (
    new_asset_id,
    new_input_image_slot_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)


def _image(**overrides: object) -> ProductInputImage:
    tenant_id = overrides.pop("tenant_id", new_tenant_id())
    product_id = overrides.pop("product_id", new_product_id())
    kwargs: dict[str, object] = {
        "input_image_slot_id": new_input_image_slot_id(),
        "asset_id": new_asset_id(),
        "created_by": new_user_id(),
        "now": utcnow(),
    }
    kwargs.update(overrides)
    return ProductInputImage.create(tenant_id, product_id, **kwargs)


def test_a_variant_image_overrides_the_products_image_for_the_same_slot() -> None:
    slot_id = new_input_image_slot_id()
    variant_id = new_product_variant_id()
    product_image = _image(input_image_slot_id=slot_id, variant_id=None)
    variant_image = _image(input_image_slot_id=slot_id, variant_id=variant_id)

    resolved = resolve_input_image(
        [product_image, variant_image], variant_id=variant_id, input_image_slot_id=slot_id
    )

    assert resolved is variant_image


def test_an_absent_variant_image_falls_back_to_the_products_image() -> None:
    slot_id = new_input_image_slot_id()
    variant_id = new_product_variant_id()
    product_image = _image(input_image_slot_id=slot_id, variant_id=None)

    resolved = resolve_input_image(
        [product_image], variant_id=variant_id, input_image_slot_id=slot_id
    )

    assert resolved is product_image


def test_a_different_variants_image_is_never_picked_up() -> None:
    slot_id = new_input_image_slot_id()
    other_variant_image = _image(input_image_slot_id=slot_id, variant_id=new_product_variant_id())

    resolved = resolve_input_image(
        [other_variant_image], variant_id=new_product_variant_id(), input_image_slot_id=slot_id
    )

    assert resolved is None


def test_no_matching_image_at_all_resolves_to_none() -> None:
    resolved = resolve_input_image(
        [], variant_id=None, input_image_slot_id=new_input_image_slot_id()
    )

    assert resolved is None
