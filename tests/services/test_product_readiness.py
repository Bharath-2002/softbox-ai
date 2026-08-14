"""Builds a real snapshot via ``spec_snapshot.build_snapshot`` (not a
hand-typed dict), the same discipline ``test_template_placeholder_validator.py``
uses, so these tests can't drift from what ``SpecResolver`` actually returns.
"""

from __future__ import annotations

from uuid import UUID

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.image_slots import InputImageSlot
from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.services.product_readiness import compute_product_readiness
from app.services.spec_snapshot import build_snapshot
from app.shared.clock import utcnow
from app.shared.ids import (
    InputImageSlotId,
    new_asset_id,
    new_category_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)

_NOW = utcnow()


def _snapshot() -> tuple[dict[str, object], str]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    fabric = AttributeDefinition.create(
        tenant_id,
        category_id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        is_required=True,
        now=_NOW,
    )
    garment_body = InputImageSlot.create(
        tenant_id, category_id, key="garment_body", label="Garment body", now=_NOW
    )
    snapshot = build_snapshot(
        attribute_definitions=[fabric],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[garment_body],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )
    return snapshot, str(garment_body.id)


def _ready_image(input_image_slot_id: str) -> ProductInputImage:
    image = ProductInputImage.create(
        new_tenant_id(),
        new_product_id(),
        input_image_slot_id=InputImageSlotId(UUID(input_image_slot_id)),
        asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=_NOW,
    )
    image.status = InputImageStatus.READY
    return image


def test_every_requirement_satisfied_is_ready() -> None:
    snapshot, slot_id = _snapshot()
    image = _ready_image(slot_id)

    result = compute_product_readiness(snapshot, attributes={"fabric": "tissue"}, images=[image])

    assert result.is_ready
    assert result.missing == []


def test_a_missing_required_attribute_is_not_ready() -> None:
    snapshot, slot_id = _snapshot()
    image = _ready_image(slot_id)

    result = compute_product_readiness(snapshot, attributes={}, images=[image])

    assert not result.is_ready
    assert "attribute:fabric" in result.missing


def test_a_missing_required_input_image_is_not_ready() -> None:
    snapshot, _slot_id = _snapshot()

    result = compute_product_readiness(snapshot, attributes={"fabric": "tissue"}, images=[])

    assert not result.is_ready
    assert any(m.startswith("input_image:") for m in result.missing)


def test_a_captured_but_unready_image_does_not_satisfy_the_requirement() -> None:
    snapshot, slot_id = _snapshot()
    image = _ready_image(slot_id)
    image.status = InputImageStatus.CAPTURED

    result = compute_product_readiness(snapshot, attributes={"fabric": "tissue"}, images=[image])

    assert not result.is_ready
    assert any(m.startswith("input_image:") for m in result.missing)


def test_an_empty_string_attribute_value_does_not_satisfy_a_required_attribute() -> None:
    snapshot, slot_id = _snapshot()
    image = _ready_image(slot_id)

    result = compute_product_readiness(snapshot, attributes={"fabric": ""}, images=[image])

    assert not result.is_ready
