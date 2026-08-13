"""Generic root->leaf, override-by-key inheritance for the taxonomy's
per-category definition rows (D10). Every M2 "definition" table -
``attribute_definitions`` first, then ``variant_axes`` and the input/catalog
image slot pools - shares this exact resolution rule: a category owns the
rows carrying its own ``category_id``, and a descendant inherits everything
from its ancestors, extending or overriding by ``key``. One generic function
instead of a near-identical copy per table.

Pure — no I/O. The caller fetches ``chain`` (``Category.ancestor_ids()``)
and ``rows`` (e.g. ``uow.attribute_definitions.list_for_categories``) and
hands both in; this only performs the merge.
"""

from __future__ import annotations

from typing import Protocol

from app.shared.ids import CategoryId


class _OwnedByCategory(Protocol):
    category_id: CategoryId
    key: str


def resolve_inherited[T: _OwnedByCategory](chain: list[CategoryId], rows: list[T]) -> dict[str, T]:
    """``chain`` is root-to-leaf, self included. A row from a category later
    in the chain overrides an earlier one with the same ``key`` — D10's
    "last-writer-wins per key" rule."""
    by_category: dict[CategoryId, list[T]] = {}
    for row in rows:
        by_category.setdefault(row.category_id, []).append(row)

    resolved: dict[str, T] = {}
    for category_id in chain:
        for row in by_category.get(category_id, []):
            resolved[row.key] = row
    return resolved
