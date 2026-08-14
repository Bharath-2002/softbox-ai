"""Golden-file test for the full composed prompt (scene substitution + role
lines), same rationale as `test_prompt_rendering.py`: a checked-in `.txt`
fixture's diff shows the rendered prompt text itself, not just test-code
noise. Inline assertions cover the behaviours a golden file wouldn't make
obvious (missing-key failures, the merge rule, no-role-lines shape).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.services.prompt_composition import compose_prompt, merge_attributes
from app.services.spec_snapshot import build_snapshot
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_category_id, new_tenant_id

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "prompt_composition"
_NOW = utcnow()


def _read_golden(name: str) -> str:
    return (_GOLDEN_DIR / name).read_text()


def test_composes_scene_substitution_and_role_lines_in_one_prompt() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    garment_body = InputImageSlot.create(
        tenant_id,
        category_id,
        key="garment_body",
        label="Garment body",
        description="Bunched detail, front-facing",
        now=_NOW,
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
    requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, garment_body.id, role="garment_body", prompt_position=0, now=_NOW
    )
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[garment_body],
        catalog_image_slots=[closeup],
        catalog_slot_input_requirements={closeup.id: [requirement]},
    )

    prompt = compose_prompt(
        snapshot,
        catalog_image_slot_id=str(closeup.id),
        prompt_template="A flat-lay of {{attr.fabric}} in {{variant.colour}}, "
        "{{input.garment_body}} shown.",
        attributes={"fabric": "Silk"},
        axis_values={"colour": "maroon"},
    )

    assert prompt + "\n" == _read_golden("scene_and_role_lines.txt")


def test_a_slot_with_no_role_lines_returns_the_scene_alone() -> None:
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )

    prompt = compose_prompt(
        snapshot,
        catalog_image_slot_id="not-a-real-id",
        prompt_template="A flat-lay of {{attr.fabric}}.",
        attributes={"fabric": "Silk"},
        axis_values={},
    )

    assert prompt == "A flat-lay of Silk."


def test_a_missing_attribute_value_is_rejected() -> None:
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )

    with pytest.raises(ValidationError):
        compose_prompt(
            snapshot,
            catalog_image_slot_id="x",
            prompt_template="{{attr.fabric}}",
            attributes={},
            axis_values={},
        )


def test_a_missing_variant_axis_value_is_rejected() -> None:
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )

    with pytest.raises(ValidationError):
        compose_prompt(
            snapshot,
            catalog_image_slot_id="x",
            prompt_template="{{variant.colour}}",
            attributes={},
            axis_values={},
        )


def test_input_placeholders_are_left_untouched_in_the_scene() -> None:
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )

    prompt = compose_prompt(
        snapshot,
        catalog_image_slot_id="not-a-real-id",
        prompt_template="Show {{input.garment_body}} clearly.",
        attributes={},
        axis_values={},
    )

    assert prompt == "Show {{input.garment_body}} clearly."


def test_merge_attributes_lets_the_variant_override_the_product() -> None:
    merged = merge_attributes({"fabric": "Silk", "border": "zari"}, {"fabric": "Cotton"})

    assert merged == {"fabric": "Cotton", "border": "zari"}
