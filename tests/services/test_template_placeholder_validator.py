"""Builds a real snapshot via ``spec_snapshot.build_snapshot`` (not a
hand-typed dict) so these tests exercise the validator against exactly the
shape ``SpecResolver`` actually returns, and can't silently drift from it.
"""

from __future__ import annotations

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.variant_axis import VariantAxis
from app.services.spec_snapshot import build_snapshot
from app.services.template_placeholder_validator import validate_template_placeholders
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id

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
        now=_NOW,
    )
    colour = VariantAxis.create(
        tenant_id, category_id, key="colour", label="Colour", affects_imagery=True, now=_NOW
    )
    bunthi = InputImageSlot.create(tenant_id, category_id, key="bunthi", label="Bunthi", now=_NOW)
    border = InputImageSlot.create(
        tenant_id, category_id, key="border_design", label="Border", now=_NOW
    )
    closeup = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    # Only `bunthi` is required by this catalog slot - `border_design` exists
    # in the pool but is not attached here, and must not resolve.
    requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, bunthi.id, role="garment_body", prompt_position=0, now=_NOW
    )

    snapshot = build_snapshot(
        attribute_definitions=[fabric],
        variant_axes=[colour],
        variant_axis_values={},
        input_image_slots=[bunthi, border],
        catalog_image_slots=[closeup],
        catalog_slot_input_requirements={closeup.id: [requirement]},
    )
    return snapshot, str(closeup.id)


def test_a_fully_resolvable_template_has_no_problems() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot,
        catalog_image_slot_id=slot_id,
        prompt_template="{{input.bunthi}} on {{attr.fabric}} in {{variant.colour}}",
    )

    assert problems == []


def test_an_input_not_required_by_this_catalog_slot_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{input.border_design}}"
    )

    assert len(problems) == 1
    assert "border_design" in problems[0]


def test_an_unknown_input_key_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{input.nonexistent}}"
    )

    assert len(problems) == 1


def test_an_unknown_attribute_key_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{attr.nonexistent}}"
    )

    assert len(problems) == 1


def test_an_unknown_variant_axis_key_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{variant.nonexistent}}"
    )

    assert len(problems) == 1


def test_an_unknown_namespace_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{scene.mood}}"
    )

    assert len(problems) == 1
    assert "namespace" in problems[0]


def test_a_malformed_placeholder_missing_the_dot_is_rejected() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="{{inputbunthi}}"
    )

    assert len(problems) == 1
    assert "Malformed" in problems[0]


def test_an_unknown_catalog_image_slot_is_rejected() -> None:
    snapshot, _slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id="not-a-real-id", prompt_template="{{input.bunthi}}"
    )

    assert len(problems) == 1
    assert "not found" in problems[0]


def test_multiple_problems_are_all_reported_not_just_the_first() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot,
        catalog_image_slot_id=slot_id,
        prompt_template="{{input.nonexistent}} and {{attr.nonexistent}}",
    )

    assert len(problems) == 2


def test_a_template_with_no_placeholders_is_valid() -> None:
    snapshot, slot_id = _snapshot()

    problems = validate_template_placeholders(
        snapshot, catalog_image_slot_id=slot_id, prompt_template="A plain scene, no placeholders."
    )

    assert problems == []
