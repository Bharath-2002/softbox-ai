"""SpecSnapshotBuilder against the in-memory fakes — resolves inheritance
(D10) across a real ancestor chain and serializes the result (D15).

``test_child_override_wins_and_only_the_winning_axis_contributes_values``
is the round-trip test D15's chunk plan calls for: build from live ->
serialize -> JSON round-trip -> assert the resolved spec matches, plus the
specific correctness property ``SpecSnapshotBuilder``'s docstring promises -
an overridden axis's *old* values must not leak into the snapshot.
"""

from __future__ import annotations

import json

import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.services.spec_snapshot_builder import SpecSnapshotBuilder
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.attribute_definition_repository import InMemoryAttributeDefinitionRepository
from tests.fakes.catalog_image_slot_repository import InMemoryCatalogImageSlotRepository
from tests.fakes.catalog_slot_input_requirement_repository import (
    InMemoryCatalogSlotInputRequirementRepository,
)
from tests.fakes.category_repository import InMemoryCategoryRepository
from tests.fakes.input_image_slot_repository import InMemoryInputImageSlotRepository
from tests.fakes.variant_axis_repository import InMemoryVariantAxisRepository
from tests.fakes.variant_axis_value_repository import InMemoryVariantAxisValueRepository


def _builder() -> tuple[
    SpecSnapshotBuilder,
    InMemoryCategoryRepository,
    InMemoryAttributeDefinitionRepository,
    InMemoryVariantAxisRepository,
    InMemoryVariantAxisValueRepository,
    InMemoryInputImageSlotRepository,
    InMemoryCatalogImageSlotRepository,
    InMemoryCatalogSlotInputRequirementRepository,
]:
    categories = InMemoryCategoryRepository()
    attribute_definitions = InMemoryAttributeDefinitionRepository()
    variant_axes = InMemoryVariantAxisRepository()
    variant_axis_values = InMemoryVariantAxisValueRepository()
    input_image_slots = InMemoryInputImageSlotRepository()
    catalog_image_slots = InMemoryCatalogImageSlotRepository()
    catalog_slot_input_requirements = InMemoryCatalogSlotInputRequirementRepository()
    builder = SpecSnapshotBuilder(
        categories,
        attribute_definitions,
        variant_axes,
        variant_axis_values,
        input_image_slots,
        catalog_image_slots,
        catalog_slot_input_requirements,
    )
    return (
        builder,
        categories,
        attribute_definitions,
        variant_axes,
        variant_axis_values,
        input_image_slots,
        catalog_image_slots,
        catalog_slot_input_requirements,
    )


async def test_unknown_category_is_not_found() -> None:
    builder, *_rest = _builder()

    with pytest.raises(NotFoundError):
        await builder.build(new_tenant_id(), new_category_id())


async def test_child_override_wins_and_only_the_winning_axis_contributes_values() -> None:
    (
        builder,
        categories,
        attribute_definitions,
        variant_axes,
        variant_axis_values,
        input_image_slots,
        catalog_image_slots,
        catalog_slot_input_requirements,
    ) = _builder()
    tenant_id = new_tenant_id()
    now = utcnow()

    parent = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=now
    )
    child = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=parent, now=now
    )
    await categories.add(parent)
    await categories.add(child)

    # Plain inheritance: the parent's own attribute is not overridden.
    care_instructions = AttributeDefinition.create(
        tenant_id,
        parent.id,
        key="care_instructions",
        label="Care instructions",
        data_type=AttributeDataType.TEXT,
        now=now,
    )
    await attribute_definitions.add(care_instructions)

    # Override: both categories define "fabric" - the child's must win.
    parent_fabric = AttributeDefinition.create(
        tenant_id,
        parent.id,
        key="fabric",
        label="Fabric (generic)",
        data_type=AttributeDataType.TEXT,
        now=now,
    )
    child_fabric = AttributeDefinition.create(
        tenant_id,
        child.id,
        key="fabric",
        label="Fabric (saree-specific)",
        data_type=AttributeDataType.TEXT,
        now=now,
    )
    await attribute_definitions.add(parent_fabric)
    await attribute_definitions.add(child_fabric)

    # Override: both categories define a "colour" axis - the child's values
    # must be the only ones in the snapshot, not the parent's.
    parent_colour = VariantAxis.create(
        tenant_id, parent.id, key="colour", label="Colour (generic)", affects_imagery=True, now=now
    )
    parent_maroon = VariantAxisValue.create(
        tenant_id, parent_colour.id, value="maroon", label="Maroon", now=now
    )
    child_colour = VariantAxis.create(
        tenant_id, child.id, key="colour", label="Colour (saree)", affects_imagery=True, now=now
    )
    child_green = VariantAxisValue.create(
        tenant_id, child_colour.id, value="green", label="Green", now=now
    )
    await variant_axes.add(parent_colour)
    await variant_axes.add(child_colour)
    await variant_axis_values.add(parent_maroon)
    await variant_axis_values.add(child_green)

    input_slot = InputImageSlot.create(
        tenant_id, parent.id, key="border_detail", label="Border detail", now=now
    )
    catalog_slot = CatalogImageSlot.create(
        tenant_id,
        parent.id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=now,
    )
    await input_image_slots.add(input_slot)
    await catalog_image_slots.add(catalog_slot)
    requirement = CatalogSlotInputRequirement.create(
        tenant_id, catalog_slot.id, input_slot.id, role="border", prompt_position=0, now=now
    )
    await catalog_slot_input_requirements.add(requirement)

    snapshot = await builder.build(tenant_id, child.id)
    round_tripped = json.loads(json.dumps(snapshot))

    attribute_keys = {d["key"]: d for d in round_tripped["attribute_definitions"]}
    assert attribute_keys["care_instructions"]["id"] == str(care_instructions.id)
    assert attribute_keys["fabric"]["id"] == str(child_fabric.id)
    assert attribute_keys["fabric"]["label"] == "Fabric (saree-specific)"

    [axis] = round_tripped["variant_axes"]
    assert axis["id"] == str(child_colour.id)
    assert [v["value"] for v in axis["values"]] == ["green"]

    [slot] = round_tripped["catalog_image_slots"]
    assert slot["id"] == str(catalog_slot.id)
    assert [r["role"] for r in slot["input_requirements"]] == ["border"]

    [input_slot_snapshot] = round_tripped["input_image_slots"]
    assert input_slot_snapshot["id"] == str(input_slot.id)
