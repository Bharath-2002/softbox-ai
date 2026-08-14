"""Renders the "role lines" half of a generation prompt (the M5 prompt
composition service's other half — scene text, attributes, variant recolour
— needs products/variants, which don't exist until M4/M5).

One line per input a catalog slot requires, in ``prompt_position`` order,
naming what the reference image at that position depicts:
``"{role}: {description}"``. Falls back to the input slot's ``label`` when
no ``description`` was ever captured, since a missing description must not
silently drop that reference from the prompt.

Pure — takes an already-resolved snapshot (the same shape
``spec_snapshot.build_snapshot`` produces), returns plain strings, does no
I/O. Same shape as ``template_placeholder_validator``: both read a catalog
slot's ``input_requirements`` and cross-reference the snapshot's
``input_image_slots[]`` by id, since a requirement row only carries the id.
"""

from __future__ import annotations

from typing import Any

from app.services.spec_snapshot import find_catalog_slot


def render_role_lines(snapshot: dict[str, Any], *, catalog_image_slot_id: str) -> list[str]:
    catalog_slot = find_catalog_slot(snapshot, catalog_image_slot_id)
    if catalog_slot is None:
        return []

    slots_by_id = {s["id"]: s for s in snapshot.get("input_image_slots", [])}
    requirements = sorted(
        catalog_slot.get("input_requirements", []), key=lambda r: r["prompt_position"]
    )

    lines: list[str] = []
    for requirement in requirements:
        slot = slots_by_id.get(requirement["input_image_slot_id"])
        if slot is None:
            continue
        text = slot.get("description") or slot["label"]
        lines.append(f"{requirement['role']}: {text}")
    return lines
