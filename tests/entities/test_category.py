from __future__ import annotations

from app.entities.category import Category
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id


def test_a_root_category_is_its_own_full_path_at_depth_zero() -> None:
    tenant_id = new_tenant_id()

    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )

    assert root.parent_id is None
    assert root.depth == 0
    assert root.path == str(root.id)


def test_a_child_category_extends_its_parents_path_by_one_depth() -> None:
    tenant_id = new_tenant_id()
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )

    child = Category.create(
        tenant_id, key="outerwear", name="Outerwear", slug="outerwear", parent=root, now=utcnow()
    )

    assert child.parent_id == root.id
    assert child.depth == 1
    assert child.path == f"{root.path}.{child.id}"


def test_a_grandchild_categorys_path_carries_the_whole_ancestor_chain() -> None:
    tenant_id = new_tenant_id()
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    child = Category.create(
        tenant_id, key="outerwear", name="Outerwear", slug="outerwear", parent=root, now=utcnow()
    )

    grandchild = Category.create(
        tenant_id, key="jackets", name="Jackets", slug="jackets", parent=child, now=utcnow()
    )

    assert grandchild.depth == 2
    assert grandchild.path == f"{root.id}.{child.id}.{grandchild.id}"


def test_a_new_category_is_active_with_no_published_or_draft_spec() -> None:
    category = Category.create(
        new_tenant_id(), key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )

    assert category.is_active is True
    assert category.current_spec_version is None
    assert category.draft_spec_version is None
