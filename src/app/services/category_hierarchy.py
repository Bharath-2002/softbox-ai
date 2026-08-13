"""Materialised-path recomputation for reparenting (D10).

Pure — no I/O, no repository, no tenant check. The caller
(``features.taxonomy.move_category.MoveCategory``) is responsible for
fetching ``category`` and its full ``subtree`` through a tenant-scoped
repository call before this runs, and for persisting the result afterward.
Kept pure so the "move a mid-tree node, every descendant's path updates"
invariant can be tested without a database in the loop.

Mutates the ``Category`` instances it is given, in place, rather than
returning replacements — ``SqlCategoryRepository.update`` follows this
codebase's established convention (``user_repository.py``) of flushing the
session's already-tracked, already-dirty instances rather than merging in
detached ones.
"""

from __future__ import annotations

from datetime import datetime

from app.entities.category import Category
from app.shared.errors import ValidationError


def reparent_subtree(
    *,
    category: Category,
    subtree: list[Category],
    new_parent: Category | None,
    now: datetime,
) -> list[Category]:
    """``subtree`` must be exactly ``category`` plus every one of its
    descendants (any order, same object instances the caller will persist).
    Returns it back, mutated: ``path`` and ``depth`` recomputed for
    ``category`` and each descendant, everything else unchanged."""
    if new_parent is not None and new_parent.id == category.id:
        raise ValidationError("A category cannot be its own parent.")

    descendant_ids = {row.id for row in subtree if row.id != category.id}
    if new_parent is not None and new_parent.id in descendant_ids:
        raise ValidationError("A category cannot be moved under its own descendant.")

    old_prefix = category.path
    new_path = f"{new_parent.path}.{category.id}" if new_parent is not None else str(category.id)
    new_depth = new_parent.depth + 1 if new_parent is not None else 0
    depth_delta = new_depth - category.depth
    new_parent_id = new_parent.id if new_parent is not None else None

    for row in subtree:
        if row.id == category.id:
            suffix = ""
        elif row.path.startswith(old_prefix + "."):
            suffix = row.path[len(old_prefix) :]
        else:
            raise ValidationError(f"{row.id} is not part of {category.id}'s subtree.")
        if row.id == category.id:
            row.parent_id = new_parent_id
        row.path = new_path + suffix
        row.depth = row.depth + depth_delta
        row.updated_at = now
    return subtree
