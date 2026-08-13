"""Pure serialization tests for ``build_snapshot`` (D15). No I/O, no
inheritance resolution — that is ``SpecSnapshotBuilder``'s job
(``test_spec_snapshot_builder.py``). This only proves the shape: every
value is JSON-safe, every resolved row keeps its own ``id`` (D15's
rename-detection needs it), and values/requirements nest under their
owning axis/slot.
"""

from __future__ import annotations

import json

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.services.spec_snapshot import build_snapshot
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id


def _empty_snapshot(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "attribute_definitions": [],
        "variant_axes": [],
        "variant_axis_values": {},
        "input_image_slots": [],
        "catalog_image_slots": [],
        "catalog_slot_input_requirements": {},
    }
    base.update(overrides)
    return base


def test_empty_spec_serializes_to_empty_lists() -> None:
    snapshot = build_snapshot(**_empty_snapshot())  # type: ignore[arg-type]

    assert snapshot == {
        "attribute_definitions": [],
        "variant_axes": [],
        "input_image_slots": [],
        "catalog_image_slots": [],
    }
    json.dumps(snapshot)


def test_attribute_definition_serializes_with_its_own_id_and_enum_values_as_strings() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    definition = AttributeDefinition.create(
        tenant_id,
        category_id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    snapshot = build_snapshot(
        **_empty_snapshot(attribute_definitions=[definition])  # type: ignore[arg-type]
    )

    [serialized] = snapshot["attribute_definitions"]
    assert serialized["id"] == str(definition.id)
    assert serialized["category_id"] == str(category_id)
    assert serialized["data_type"] == "text"
    assert serialized["semantic_role"] is None
    json.dumps(snapshot)


def test_variant_axis_values_nest_under_their_owning_axis() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    axis = VariantAxis.create(
        tenant_id, category_id, key="colour", label="Colour", affects_imagery=True, now=utcnow()
    )
    value = VariantAxisValue.create(
        tenant_id, axis.id, value="maroon", label="Maroon", now=utcnow()
    )

    snapshot = build_snapshot(
        **_empty_snapshot(  # type: ignore[arg-type]
            variant_axes=[axis], variant_axis_values={axis.id: [value]}
        )
    )

    [serialized_axis] = snapshot["variant_axes"]
    assert serialized_axis["id"] == str(axis.id)
    [serialized_value] = serialized_axis["values"]
    assert serialized_value["id"] == str(value.id)
    assert serialized_value["value"] == "maroon"
    json.dumps(snapshot)


def test_an_axis_with_no_entry_in_the_values_lookup_serializes_with_an_empty_list() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    axis = VariantAxis.create(
        tenant_id, category_id, key="size", label="Size", affects_imagery=False, now=utcnow()
    )

    snapshot = build_snapshot(**_empty_snapshot(variant_axes=[axis]))  # type: ignore[arg-type]

    assert snapshot["variant_axes"][0]["values"] == []


def test_catalog_slot_input_requirements_nest_under_their_owning_slot_ordered_by_position() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    catalog_slot = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )
    input_slot = InputImageSlot.create(
        tenant_id, category_id, key="border", label="Border", now=utcnow()
    )
    second_requirement = CatalogSlotInputRequirement.create(
        tenant_id,
        catalog_slot.id,
        input_slot.id,
        role="border_detail",
        prompt_position=1,
        now=utcnow(),
    )
    first_requirement = CatalogSlotInputRequirement.create(
        tenant_id,
        catalog_slot.id,
        input_slot.id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )

    snapshot = build_snapshot(
        **_empty_snapshot(  # type: ignore[arg-type]
            catalog_image_slots=[catalog_slot],
            catalog_slot_input_requirements={
                catalog_slot.id: [second_requirement, first_requirement]
            },
        )
    )

    [serialized_slot] = snapshot["catalog_image_slots"]
    assert serialized_slot["id"] == str(catalog_slot.id)
    assert [r["role"] for r in serialized_slot["input_requirements"]] == [
        "garment_body",
        "border_detail",
    ]
    json.dumps(snapshot)


def test_input_image_slot_serializes_null_example_asset_id_when_absent() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    slot = InputImageSlot.create(tenant_id, category_id, key="border", label="Border", now=utcnow())

    snapshot = build_snapshot(**_empty_snapshot(input_image_slots=[slot]))  # type: ignore[arg-type]

    assert snapshot["input_image_slots"][0]["example_asset_id"] is None
