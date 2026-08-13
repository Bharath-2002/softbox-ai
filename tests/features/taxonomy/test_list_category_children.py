from __future__ import annotations

from datetime import UTC, datetime

from app.entities.category import Category
from app.features.taxonomy.list_category_children import ListCategoryChildren
from app.shared.ids import new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_lists_root_categories_when_parent_id_is_none() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListCategoryChildren(uow_factory)
    tenant_id = new_tenant_id()
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(root)

    roots = await use_case(tenant_id=tenant_id, parent_id=None)

    assert [c.id for c in roots] == [root.id]


async def test_lists_a_categorys_direct_children() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListCategoryChildren(uow_factory)
    tenant_id = new_tenant_id()
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    child = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=root, now=_NOW
    )
    await uow_factory.categories.add(root)
    await uow_factory.categories.add(child)

    children = await use_case(tenant_id=tenant_id, parent_id=root.id)

    assert [c.id for c in children] == [child.id]
