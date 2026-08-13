"""Cursor pagination: opaque, round-trips exactly, and rejects tampering.

No paginated resource exists yet (M1 chunk 5) — this exercises the helper
directly rather than inventing one to page through.
"""

from __future__ import annotations

import base64
import uuid

import pytest

from app.shared.errors import ValidationError
from app.shared.pagination import Cursor, decode_cursor, encode_cursor


def test_round_trips_a_string_sort_key() -> None:
    row_id = uuid.uuid4()
    cursor = Cursor(sort_key="2026-08-14T10:00:00+00:00", id=row_id)

    decoded = decode_cursor(encode_cursor(cursor))

    assert decoded == cursor


def test_round_trips_a_numeric_sort_key() -> None:
    row_id = uuid.uuid4()
    cursor = Cursor(sort_key=42, id=row_id)

    decoded = decode_cursor(encode_cursor(cursor))

    assert decoded == cursor


def test_two_rows_with_the_same_sort_key_decode_to_different_ids() -> None:
    """The tiebreaker actually survives the round trip — a cursor collapsed
    to just the sort key would make two such cursors indistinguishable."""
    shared_sort_key = "2026-08-14T10:00:00+00:00"
    first = Cursor(sort_key=shared_sort_key, id=uuid.uuid4())
    second = Cursor(sort_key=shared_sort_key, id=uuid.uuid4())

    decoded_first = decode_cursor(encode_cursor(first))
    decoded_second = decode_cursor(encode_cursor(second))

    assert decoded_first.sort_key == decoded_second.sort_key
    assert decoded_first.id != decoded_second.id


def test_a_cursor_is_opaque_base64_not_readable_json() -> None:
    cursor = Cursor(sort_key="secret-ordering-value", id=uuid.uuid4())

    token = encode_cursor(cursor)

    with pytest.raises((ValueError, UnicodeDecodeError)):
        # A client should not be able to treat this as plain JSON and edit
        # the sort key directly - it must go through base64 first.
        import json

        json.loads(token)


def test_garbage_input_is_rejected_as_a_validation_error() -> None:
    with pytest.raises(ValidationError, match="Invalid pagination cursor"):
        decode_cursor("not-a-real-cursor-!!!")


def test_valid_base64_that_is_not_the_expected_json_shape_is_rejected() -> None:
    tampered = base64.urlsafe_b64encode(b'{"unexpected": "shape"}').decode("ascii")

    with pytest.raises(ValidationError, match="Invalid pagination cursor"):
        decode_cursor(tampered)


def test_a_non_uuid_id_field_is_rejected() -> None:
    tampered = base64.urlsafe_b64encode(b'{"k": "x", "id": "not-a-uuid"}').decode("ascii")

    with pytest.raises(ValidationError, match="Invalid pagination cursor"):
        decode_cursor(tampered)


def test_empty_string_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Invalid pagination cursor"):
        decode_cursor("")
