"""Cursor pagination (CLAUDE.md §9): opaque, not an offset.

A cursor encodes the last row's sort value together with its id — the id is
a tiebreaker for rows that share a sort value, which happens often enough on
a timestamp column to matter. Encoding both as one opaque base64 token,
rather than exposing either directly in the query string, means a client
cannot edit a raw timestamp to jump to an arbitrary position in a listing it
should not be able to construct itself.

Lives in `shared`, not `api` (see CLAUDE.md §1's layer table) — nothing here
depends on FastAPI or Pydantic, and a background job walking a paginated
result set has the same need to encode and decode a cursor.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.shared.errors import ValidationError


@dataclass(frozen=True)
class Cursor:
    sort_key: Any
    id: UUID


@dataclass(frozen=True)
class Page[T]:
    """A page of results plus the cursor to fetch the next one — ``None``
    means this was the last page. A repository asked for ``limit`` rows
    should be handed ``limit + 1`` by its caller so ``has_more`` can be
    determined without a separate ``COUNT`` query; building the ``Page``
    itself (trimming the extra row, encoding ``next_cursor`` from the last
    *returned* row) is the use case's job, not this dataclass's."""

    items: list[T]
    next_cursor: str | None


def encode_cursor(cursor: Cursor) -> str:
    payload = json.dumps({"k": cursor.sort_key, "id": str(cursor.id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(token: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        data = json.loads(raw)
        return Cursor(sort_key=data["k"], id=UUID(data["id"]))
    except (ValueError, KeyError, TypeError) as exc:
        # binascii.Error and json.JSONDecodeError are both ValueError
        # subclasses; a missing "k"/"id" key raises KeyError; a non-string
        # "id" raises TypeError from UUID(). All three mean the same thing
        # to the caller: this token was not one we issued.
        raise ValidationError("Invalid pagination cursor.") from exc
