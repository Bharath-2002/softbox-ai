"""The generic root->leaf, override-by-key resolver (D10). Uses
``AttributeDefinition`` as the first real consumer, but the function itself
is generic — see the module's own docstring.
"""

from __future__ import annotations

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.category import Category
from app.services.spec_inheritance import resolve_inherited
from app.shared.clock import utcnow
from app.shared.ids import CategoryId, new_category_id, new_tenant_id


def _tree() -> tuple[Category, Category, Category]:
    tenant_id = new_tenant_id()
    root = Category.create(tenant_id, key="a", name="A", slug="a", parent=None, now=utcnow())
    mid = Category.create(tenant_id, key="b", name="B", slug="b", parent=root, now=utcnow())
    leaf = Category.create(tenant_id, key="c", name="C", slug="c", parent=mid, now=utcnow())
    return root, mid, leaf


def _definition(category: Category, key: str, label: str) -> AttributeDefinition:
    return AttributeDefinition.create(
        category.tenant_id,
        category.id,
        key=key,
        label=label,
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )


def test_a_leaf_inherits_every_ancestors_definitions() -> None:
    root, mid, leaf = _tree()
    rows = [
        _definition(root, "fabric", "Fabric (root)"),
        _definition(mid, "weave", "Weave (mid)"),
        _definition(leaf, "finish", "Finish (leaf)"),
    ]

    resolved = resolve_inherited(leaf.ancestor_ids(), rows)

    assert set(resolved) == {"fabric", "weave", "finish"}


def test_a_more_specific_category_overrides_an_inherited_key() -> None:
    root, _mid, leaf = _tree()
    rows = [
        _definition(root, "fabric", "Fabric (root)"),
        _definition(leaf, "fabric", "Fabric (leaf override)"),
    ]

    resolved = resolve_inherited(leaf.ancestor_ids(), rows)

    assert resolved["fabric"].label == "Fabric (leaf override)"


def test_a_mid_level_override_beats_root_but_not_a_deeper_leaf_override() -> None:
    root, mid, leaf = _tree()
    rows = [
        _definition(root, "fabric", "Fabric (root)"),
        _definition(mid, "fabric", "Fabric (mid override)"),
    ]

    resolved_at_mid = resolve_inherited(mid.ancestor_ids(), rows)
    resolved_at_leaf = resolve_inherited(leaf.ancestor_ids(), rows)

    assert resolved_at_mid["fabric"].label == "Fabric (mid override)"
    assert resolved_at_leaf["fabric"].label == "Fabric (mid override)"


def test_a_sibling_subtrees_definitions_are_not_inherited() -> None:
    root, _mid, leaf = _tree()
    unrelated_category_id = CategoryId(new_category_id())
    unrelated = AttributeDefinition.create(
        root.tenant_id,
        unrelated_category_id,
        key="unrelated",
        label="Unrelated",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    resolved = resolve_inherited(leaf.ancestor_ids(), [unrelated])

    assert resolved == {}


def test_a_root_category_resolves_only_its_own_definitions() -> None:
    root, _mid, _leaf = _tree()
    rows = [_definition(root, "fabric", "Fabric")]

    resolved = resolve_inherited(root.ancestor_ids(), rows)

    assert set(resolved) == {"fabric"}
