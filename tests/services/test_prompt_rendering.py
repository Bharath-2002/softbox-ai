"""Golden-file tests for role-line rendering (CHECKLIST.md M3). Comparing
against a checked-in ``.txt`` fixture, rather than asserting on the return
value inline, catches accidental formatting drift (a stray space, a changed
separator) that an inline string-equality assertion would still show clearly
but that a reviewer skimming a diff of *test code* could miss — the golden
file's diff is the rendered prompt text itself.
"""

from __future__ import annotations

from pathlib import Path

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.services.prompt_rendering import render_role_lines
from app.services.spec_snapshot import build_snapshot
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id

_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "golden" / "prompt_rendering"
_NOW = utcnow()


def _read_golden(name: str) -> str:
    return (_GOLDEN_DIR / name).read_text()


def test_role_lines_are_ordered_by_prompt_position_not_creation_order() -> None:
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
    border_detail = InputImageSlot.create(
        tenant_id,
        category_id,
        key="border_detail",
        label="Border detail",
        description="Border trim, flat",
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
    # Created in reverse of the intended reading order - only prompt_position
    # decides the render order, not requirement-list order.
    border_requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, border_detail.id, role="border_detail", prompt_position=1, now=_NOW
    )
    body_requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, garment_body.id, role="garment_body", prompt_position=0, now=_NOW
    )

    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[garment_body, border_detail],
        catalog_image_slots=[closeup],
        catalog_slot_input_requirements={closeup.id: [border_requirement, body_requirement]},
    )

    lines = render_role_lines(snapshot, catalog_image_slot_id=str(closeup.id))

    assert "\n".join(lines) + "\n" == _read_golden("two_requirements.txt")


def test_a_missing_description_falls_back_to_the_slot_label() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    garment_body = InputImageSlot.create(
        tenant_id, category_id, key="garment_body", label="Garment body", now=_NOW
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

    lines = render_role_lines(snapshot, catalog_image_slot_id=str(closeup.id))

    assert "\n".join(lines) + "\n" == _read_golden("falls_back_to_label.txt")


def test_an_unknown_catalog_slot_renders_no_lines() -> None:
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[],
        catalog_slot_input_requirements={},
    )

    assert render_role_lines(snapshot, catalog_image_slot_id="not-a-real-id") == []
