from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.shared.clock import utcnow
from app.shared.ids import new_catalog_image_slot_id, new_input_image_slot_id, new_tenant_id


def test_a_requirement_is_required_by_default() -> None:
    requirement = CatalogSlotInputRequirement.create(
        new_tenant_id(),
        new_catalog_image_slot_id(),
        new_input_image_slot_id(),
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )

    assert requirement.is_required is True
    assert requirement.role == "garment_body"
    assert requirement.prompt_position == 0


def test_a_requirement_can_be_declared_optional() -> None:
    requirement = CatalogSlotInputRequirement.create(
        new_tenant_id(),
        new_catalog_image_slot_id(),
        new_input_image_slot_id(),
        role="border_detail",
        prompt_position=1,
        is_required=False,
        now=utcnow(),
    )

    assert requirement.is_required is False
