"""Classifies the difference between two D15 spec snapshots
(``spec_snapshot.build_snapshot`` output) into the four change classes D15
defines. Pure — no I/O.

Only ``attribute_definitions``, ``input_image_slots`` and
``catalog_image_slots`` are classified — the three row kinds D15's change
table actually defines behaviour for. ``variant_axes`` changing membership
is orthogonal (it changes which variant combinations exist, not which data
a product needs to supply) and D15 states no policy for it; revisit if that
gap ever blocks real work.

Every row kind is matched by its stable ``id`` (not ``key``) across the two
snapshots — the same id appearing under a different key *is* what "rename a
key is not permitted" (D15) means, and is only detectable this way.

``catalog_image_slots`` never classify as ``ADDED_REQUIRED`` regardless of
their own ``is_required`` flag — D15 gives a new catalog slot its own
auto-apply-with-backfill-offer behaviour, not the needs-attention path a
required attribute or input slot gets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SpecChangeType(StrEnum):
    ADDED_OPTIONAL = "added_optional"
    ADDED_REQUIRED = "added_required"
    RETIRED = "retired"
    RENAMED = "renamed"


@dataclass(frozen=True)
class SpecChange:
    change_type: SpecChangeType
    row_kind: str
    row_id: str
    key: str
    previous_key: str | None = None


_ROW_KINDS: tuple[tuple[str, str, bool], ...] = (
    ("attribute_definitions", "attribute_definition", True),
    ("input_image_slots", "input_image_slot", True),
    ("catalog_image_slots", "catalog_image_slot", False),
)


def classify_changes(
    previous: dict[str, Any] | None, next_snapshot: dict[str, Any]
) -> list[SpecChange]:
    """``previous`` is ``None`` for a category's first publish — every row
    in ``next_snapshot`` is then necessarily an addition, never a rename or
    a retirement."""
    changes: list[SpecChange] = []
    for section, row_kind, honours_required in _ROW_KINDS:
        changes.extend(
            _classify_section(previous, next_snapshot, section, row_kind, honours_required)
        )
    return changes


def _classify_section(
    previous: dict[str, Any] | None,
    next_snapshot: dict[str, Any],
    section: str,
    row_kind: str,
    honours_required: bool,
) -> list[SpecChange]:
    previous_rows: dict[str, dict[str, Any]] = (
        {} if previous is None else {row["id"]: row for row in previous.get(section, [])}
    )
    next_rows: dict[str, dict[str, Any]] = {
        row["id"]: row for row in next_snapshot.get(section, [])
    }

    changes: list[SpecChange] = []
    for row_id, row in next_rows.items():
        previous_row = previous_rows.get(row_id)
        if previous_row is None:
            change_type = (
                SpecChangeType.ADDED_REQUIRED
                if honours_required and row.get("is_required")
                else SpecChangeType.ADDED_OPTIONAL
            )
            changes.append(SpecChange(change_type, row_kind, row_id, row["key"]))
        elif previous_row["key"] != row["key"]:
            changes.append(
                SpecChange(
                    SpecChangeType.RENAMED,
                    row_kind,
                    row_id,
                    row["key"],
                    previous_key=previous_row["key"],
                )
            )

    for row_id, previous_row in previous_rows.items():
        if row_id not in next_rows:
            changes.append(
                SpecChange(SpecChangeType.RETIRED, row_kind, row_id, previous_row["key"])
            )

    return changes


def summarize(changes: list[SpecChange]) -> dict[str, Any]:
    """The JSON-safe shape stored in ``category_spec_versions.change_summary``."""
    return {
        "changes": [
            {
                "change_type": change.change_type.value,
                "row_kind": change.row_kind,
                "row_id": change.row_id,
                "key": change.key,
                "previous_key": change.previous_key,
            }
            for change in changes
        ]
    }
