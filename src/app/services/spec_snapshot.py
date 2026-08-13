"""Serializes a resolved category spec (D10's inheritance-merged view of
D11-D13's definition tables) into the JSON-safe shape D15's
``category_spec_versions.snapshot`` stores.

Pure — takes already-resolved domain objects and lookups, returns plain
dicts of JSON-safe values (``str``/``int``/``bool``/``None``/``dict``/
``list``), never a domain object or an enum member, so ``json.dumps`` on the
result never raises and a stored snapshot never depends on how an entity's
``__repr__`` happens to work today. Fetching and inheritance resolution are
the caller's job — see ``services.spec_snapshot_builder.SpecSnapshotBuilder``.

Every resolved row's own ``id`` is included, not just its ``key`` — D15's
"rename a key is not permitted" rule is only detectable as "same id,
different key" across two snapshots; a key-only snapshot makes a rename
indistinguishable from retire+add.
"""

from __future__ import annotations

from typing import Any

from app.entities.attribute_definition import AttributeDefinition
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.shared.ids import CatalogImageSlotId, VariantAxisId


def _serialize_attribute_definition(definition: AttributeDefinition) -> dict[str, Any]:
    return {
        "id": str(definition.id),
        "category_id": str(definition.category_id),
        "key": definition.key,
        "label": definition.label,
        "help_text": definition.help_text,
        "data_type": definition.data_type.value,
        "semantic_role": definition.semantic_role.value if definition.semantic_role else None,
        "is_required": definition.is_required,
        "is_filterable": definition.is_filterable,
        "is_public": definition.is_public,
        "position": definition.position,
        "validation": definition.validation,
        "ui": definition.ui,
        "default_value": definition.default_value,
    }


def _serialize_variant_axis_value(value: VariantAxisValue) -> dict[str, Any]:
    return {
        "id": str(value.id),
        "value": value.value,
        "label": value.label,
        "metadata": value.metadata,
    }


def _serialize_variant_axis(axis: VariantAxis, values: list[VariantAxisValue]) -> dict[str, Any]:
    return {
        "id": str(axis.id),
        "category_id": str(axis.category_id),
        "key": axis.key,
        "label": axis.label,
        "position": axis.position,
        "affects_imagery": axis.affects_imagery,
        "values": [_serialize_variant_axis_value(value) for value in values],
    }


def _serialize_input_image_slot(slot: InputImageSlot) -> dict[str, Any]:
    return {
        "id": str(slot.id),
        "category_id": str(slot.category_id),
        "key": slot.key,
        "label": slot.label,
        "description": slot.description,
        "capture_guidance": slot.capture_guidance,
        "example_asset_id": str(slot.example_asset_id) if slot.example_asset_id else None,
        "normalisation": slot.normalisation,
        "is_required": slot.is_required,
        "position": slot.position,
    }


def _serialize_requirement(requirement: CatalogSlotInputRequirement) -> dict[str, Any]:
    return {
        "input_image_slot_id": str(requirement.input_image_slot_id),
        "role": requirement.role,
        "prompt_position": requirement.prompt_position,
        "is_required": requirement.is_required,
    }


def _serialize_catalog_image_slot(
    slot: CatalogImageSlot, requirements: list[CatalogSlotInputRequirement]
) -> dict[str, Any]:
    return {
        "id": str(slot.id),
        "category_id": str(slot.category_id),
        "key": slot.key,
        "label": slot.label,
        "description": slot.description,
        "position": slot.position,
        "aspect_ratio": slot.aspect_ratio,
        "target_width": slot.target_width,
        "target_height": slot.target_height,
        "is_required": slot.is_required,
        "input_requirements": sorted(
            (_serialize_requirement(r) for r in requirements),
            key=lambda r: r["prompt_position"],
        ),
    }


def build_snapshot(
    *,
    attribute_definitions: list[AttributeDefinition],
    variant_axes: list[VariantAxis],
    variant_axis_values: dict[VariantAxisId, list[VariantAxisValue]],
    input_image_slots: list[InputImageSlot],
    catalog_image_slots: list[CatalogImageSlot],
    catalog_slot_input_requirements: dict[CatalogImageSlotId, list[CatalogSlotInputRequirement]],
) -> dict[str, Any]:
    """``variant_axis_values``/``catalog_slot_input_requirements`` are keyed
    by the *winning* axis/slot id only — values and requirements are not
    category-owned (D12/D13), so ``spec_inheritance.resolve_inherited``
    does not apply to them; the caller must have already discarded any
    axis/slot an inheriting category overrode before fetching these."""
    return {
        "attribute_definitions": [
            _serialize_attribute_definition(d) for d in attribute_definitions
        ],
        "variant_axes": [
            _serialize_variant_axis(axis, variant_axis_values.get(axis.id, []))
            for axis in variant_axes
        ],
        "input_image_slots": [_serialize_input_image_slot(s) for s in input_image_slots],
        "catalog_image_slots": [
            _serialize_catalog_image_slot(slot, catalog_slot_input_requirements.get(slot.id, []))
            for slot in catalog_image_slots
        ],
    }
