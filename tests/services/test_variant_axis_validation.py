from __future__ import annotations

from app.services.variant_axis_validation import validate_axis_values

_SNAPSHOT = {
    "variant_axes": [
        {
            "id": "axis-1",
            "key": "colour",
            "label": "Colour",
            "position": 0,
            "affects_imagery": True,
            "values": [
                {"id": "v1", "value": "maroon", "label": "Maroon", "metadata": {}},
                {"id": "v2", "value": "teal", "label": "Teal", "metadata": {}},
            ],
        },
        {
            "id": "axis-2",
            "key": "size",
            "label": "Size",
            "position": 1,
            "affects_imagery": False,
            "values": [],
        },
    ]
}


def test_a_known_axis_with_an_allowed_value_has_no_problems() -> None:
    assert validate_axis_values(_SNAPSHOT, {"colour": "maroon"}) == []


def test_an_axis_with_no_declared_values_accepts_any_string() -> None:
    assert validate_axis_values(_SNAPSHOT, {"size": "XL"}) == []


def test_an_unknown_axis_key_is_a_problem() -> None:
    problems = validate_axis_values(_SNAPSHOT, {"fabric": "silk"})
    assert len(problems) == 1
    assert "fabric" in problems[0]


def test_a_disallowed_value_for_a_known_axis_is_a_problem() -> None:
    problems = validate_axis_values(_SNAPSHOT, {"colour": "gold"})
    assert len(problems) == 1
    assert "gold" in problems[0]
    assert "colour" in problems[0]
