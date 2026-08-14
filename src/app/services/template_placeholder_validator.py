"""D14a — validate a template's ``prompt_template`` placeholders at
analysis time, against a *resolved* category spec snapshot (the same
snapshot shape ``spec_snapshot.build_snapshot`` produces and
``SpecResolver`` returns) — never against the live tables. Pure: takes
already-resolved data, returns problem strings, does no I/O.

A placeholder is ``{{namespace.key}}`` for one of three namespaces:

- ``{{input.<key>}}`` — must name an input slot declared in *this specific
  catalog slot's* ``input_requirements`` (D13's sharing join). A slot that
  exists in the category's input pool but isn't required by this catalog
  slot does not count — the whole point of the join is that a catalog slot
  only draws the inputs it actually asked for.
- ``{{attr.<key>}}`` — must name one of the snapshot's attribute
  definitions.
- ``{{variant.<key>}}`` — must name one of the snapshot's variant axes.

The snapshot's ``catalog_image_slots[].input_requirements`` entries carry
only ``input_image_slot_id`` (see ``spec_snapshot._serialize_requirement``)
— not the input slot's ``key`` — so resolving ``{{input.<key>}}`` needs a
second lookup through the snapshot's own ``input_image_slots[]`` array to
turn each required id into its key. Both arrays come from the same
snapshot; nothing here reaches past it.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.spec_snapshot import find_catalog_slot

PLACEHOLDER_PATTERN = re.compile(r"\{\{(.*?)\}\}")
PLACEHOLDER_SHAPE_PATTERN = re.compile(r"^\s*([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\s*$")
_NAMESPACES = frozenset({"input", "attr", "variant"})


def validate_template_placeholders(
    snapshot: dict[str, Any], *, catalog_image_slot_id: str, prompt_template: str
) -> list[str]:
    """Returns a list of human-readable problems. An empty list means every
    placeholder resolved — the template may reach ``analysed``."""
    catalog_slot = find_catalog_slot(snapshot, catalog_image_slot_id)
    if catalog_slot is None:
        return [f"Catalog image slot {catalog_image_slot_id!r} not found in this spec."]

    slot_key_by_id = {s["id"]: s["key"] for s in snapshot.get("input_image_slots", [])}
    required_input_keys = {
        slot_key_by_id[r["input_image_slot_id"]]
        for r in catalog_slot.get("input_requirements", [])
        if r["input_image_slot_id"] in slot_key_by_id
    }
    attribute_keys = {d["key"] for d in snapshot.get("attribute_definitions", [])}
    variant_keys = {a["key"] for a in snapshot.get("variant_axes", [])}

    problems: list[str] = []
    for raw_match in PLACEHOLDER_PATTERN.finditer(prompt_template):
        body = raw_match.group(1)
        shape_match = PLACEHOLDER_SHAPE_PATTERN.match(body)
        if shape_match is None:
            problems.append(
                f"Malformed placeholder {{{{{body}}}}} - expected {{{{namespace.key}}}}."
            )
            continue

        namespace, key = shape_match.group(1), shape_match.group(2)
        if namespace not in _NAMESPACES:
            problems.append(f"Unknown placeholder namespace {{{{{namespace}.{key}}}}}.")
        elif namespace == "input" and key not in required_input_keys:
            problems.append(
                f"{{{{input.{key}}}}} does not resolve to an input this catalog slot requires."
            )
        elif namespace == "attr" and key not in attribute_keys:
            problems.append(f"{{{{attr.{key}}}}} does not resolve to an attribute in this spec.")
        elif namespace == "variant" and key not in variant_keys:
            problems.append(
                f"{{{{variant.{key}}}}} does not resolve to a variant axis in this spec."
            )

    return problems
