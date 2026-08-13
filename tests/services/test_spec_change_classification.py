"""Pure classification tests (D15) - synthetic snapshot dicts, no
``SpecSnapshotBuilder``/DB involved, so each of the four change classes can
be exercised directly without needing a real "retire" or "rename" feature
to exist yet.
"""

from __future__ import annotations

from app.services.spec_change_classification import (
    SpecChangeType,
    classify_changes,
    summarize,
)


def _row(row_id: str, key: str, *, is_required: bool = False) -> dict[str, object]:
    return {"id": row_id, "key": key, "is_required": is_required}


def _snapshot(**sections: list[dict[str, object]]) -> dict[str, object]:
    base: dict[str, object] = {
        "attribute_definitions": [],
        "input_image_slots": [],
        "catalog_image_slots": [],
    }
    base.update(sections)
    return base


def test_first_publish_classifies_every_row_as_added() -> None:
    next_snapshot = _snapshot(
        attribute_definitions=[_row("a1", "fabric", is_required=False)],
        input_image_slots=[_row("i1", "border", is_required=True)],
    )

    changes = classify_changes(None, next_snapshot)

    assert {(c.row_id, c.change_type) for c in changes} == {
        ("a1", SpecChangeType.ADDED_OPTIONAL),
        ("i1", SpecChangeType.ADDED_REQUIRED),
    }


def test_a_new_optional_attribute_is_added_optional() -> None:
    previous = _snapshot()
    next_snapshot = _snapshot(attribute_definitions=[_row("a1", "fabric", is_required=False)])

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.ADDED_OPTIONAL
    assert change.row_kind == "attribute_definition"


def test_a_new_required_attribute_is_added_required() -> None:
    previous = _snapshot()
    next_snapshot = _snapshot(attribute_definitions=[_row("a1", "fabric", is_required=True)])

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.ADDED_REQUIRED


def test_a_new_required_input_slot_is_added_required() -> None:
    previous = _snapshot()
    next_snapshot = _snapshot(input_image_slots=[_row("i1", "border", is_required=True)])

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.ADDED_REQUIRED
    assert change.row_kind == "input_image_slot"


def test_a_new_catalog_slot_is_always_added_optional_even_when_required() -> None:
    previous = _snapshot()
    next_snapshot = _snapshot(catalog_image_slots=[_row("c1", "closeup", is_required=True)])

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.ADDED_OPTIONAL
    assert change.row_kind == "catalog_image_slot"


def test_a_row_missing_from_the_next_snapshot_is_retired() -> None:
    previous = _snapshot(attribute_definitions=[_row("a1", "fabric")])
    next_snapshot = _snapshot()

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.RETIRED
    assert change.row_id == "a1"
    assert change.key == "fabric"


def test_same_id_different_key_is_renamed() -> None:
    previous = _snapshot(attribute_definitions=[_row("a1", "fabric")])
    next_snapshot = _snapshot(attribute_definitions=[_row("a1", "material")])

    [change] = classify_changes(previous, next_snapshot)

    assert change.change_type is SpecChangeType.RENAMED
    assert change.previous_key == "fabric"
    assert change.key == "material"


def test_an_unchanged_row_produces_no_change() -> None:
    previous = _snapshot(attribute_definitions=[_row("a1", "fabric")])
    next_snapshot = _snapshot(attribute_definitions=[_row("a1", "fabric")])

    assert classify_changes(previous, next_snapshot) == []


def test_summarize_is_json_safe_and_preserves_every_change() -> None:
    previous = _snapshot(attribute_definitions=[_row("a1", "fabric")])
    next_snapshot = _snapshot(attribute_definitions=[_row("a1", "material")])
    changes = classify_changes(previous, next_snapshot)

    summary = summarize(changes)

    assert summary == {
        "changes": [
            {
                "change_type": "renamed",
                "row_kind": "attribute_definition",
                "row_id": "a1",
                "key": "material",
                "previous_key": "fabric",
            }
        ]
    }
