from __future__ import annotations

import pytest

from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_category_id, new_tenant_id


def test_a_new_input_slot_is_required_by_default() -> None:
    slot = InputImageSlot.create(
        new_tenant_id(), new_category_id(), key="border_detail", label="Border detail", now=utcnow()
    )

    assert slot.is_required is True
    assert slot.normalisation == {}
    assert slot.example_asset_id is None


def test_an_input_slot_key_that_is_not_a_safe_identifier_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Input image slot key"):
        InputImageSlot.create(
            new_tenant_id(),
            new_category_id(),
            key="Border Detail",
            label="Border detail",
            now=utcnow(),
        )


def test_a_new_catalog_slot_carries_its_target_dimensions() -> None:
    slot = CatalogImageSlot.create(
        new_tenant_id(),
        new_category_id(),
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )

    assert slot.aspect_ratio == "4:5"
    assert slot.target_width == 1080
    assert slot.target_height == 1350
    assert slot.is_required is True


def test_a_catalog_slot_key_that_is_not_a_safe_identifier_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Catalog image slot key"):
        CatalogImageSlot.create(
            new_tenant_id(),
            new_category_id(),
            key="Close Up",
            label="Close-up",
            aspect_ratio="4:5",
            target_width=1080,
            target_height=1350,
            now=utcnow(),
        )
