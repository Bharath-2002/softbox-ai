"""The invariant that makes a materialised path worth having: move a node,
every descendant's path updates with it. Pure — no database, per the
module's own docstring.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.services.category_hierarchy import reparent_subtree
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_tenant_id

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _tree() -> tuple[Category, Category, Category, Category]:
    """root -> mid -> leaf, plus an unrelated sibling of root."""
    tenant_id = new_tenant_id()
    root = Category.create(tenant_id, key="a", name="A", slug="a", parent=None, now=utcnow())
    mid = Category.create(tenant_id, key="b", name="B", slug="b", parent=root, now=utcnow())
    leaf = Category.create(tenant_id, key="c", name="C", slug="c", parent=mid, now=utcnow())
    other_root = Category.create(tenant_id, key="d", name="D", slug="d", parent=None, now=utcnow())
    return root, mid, leaf, other_root


def test_moving_a_mid_tree_node_updates_every_descendants_path() -> None:
    _root, mid, leaf, other_root = _tree()
    subtree = [mid, leaf]

    reparent_subtree(category=mid, subtree=subtree, new_parent=other_root, now=NOW)

    assert mid.parent_id == other_root.id
    assert mid.path == f"{other_root.path}.{mid.id}"
    assert mid.depth == other_root.depth + 1
    assert leaf.path == f"{mid.path}.{leaf.id}"
    assert leaf.depth == mid.depth + 1
    assert leaf.parent_id == mid.id  # unchanged - leaf's direct parent is still mid


def test_moving_a_node_to_root_clears_its_parent_and_resets_depth() -> None:
    _root, mid, leaf, _other_root = _tree()

    reparent_subtree(category=mid, subtree=[mid, leaf], new_parent=None, now=NOW)

    assert mid.parent_id is None
    assert mid.depth == 0
    assert mid.path == str(mid.id)
    assert leaf.path == f"{mid.id}.{leaf.id}"
    assert leaf.depth == 1


def test_every_updated_row_gets_the_same_updated_at() -> None:
    _root, mid, leaf, other_root = _tree()

    reparent_subtree(category=mid, subtree=[mid, leaf], new_parent=other_root, now=NOW)

    assert mid.updated_at == NOW
    assert leaf.updated_at == NOW


def test_a_category_cannot_become_its_own_parent() -> None:
    _root, mid, leaf, _other_root = _tree()

    with pytest.raises(ValidationError, match="own parent"):
        reparent_subtree(category=mid, subtree=[mid, leaf], new_parent=mid, now=NOW)


def test_a_category_cannot_be_moved_under_its_own_descendant() -> None:
    _root, mid, leaf, _other_root = _tree()

    with pytest.raises(ValidationError, match="own descendant"):
        reparent_subtree(category=mid, subtree=[mid, leaf], new_parent=leaf, now=NOW)


def test_a_row_not_in_the_declared_subtree_is_rejected() -> None:
    _root, mid, _leaf, other_root = _tree()

    with pytest.raises(ValidationError, match="not part of"):
        reparent_subtree(category=mid, subtree=[mid, other_root], new_parent=None, now=NOW)
