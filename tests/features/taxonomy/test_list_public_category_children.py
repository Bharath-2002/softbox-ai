from __future__ import annotations

from datetime import UTC, datetime

from app.entities.category import Category
from app.features.taxonomy.list_public_category_children import ListPublicCategoryChildren
from app.shared.ids import new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_lists_active_root_categories() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    active = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(active)
    use_case = ListPublicCategoryChildren(uow_factory)

    categories = await use_case(tenant_id=tenant_id, parent_id=None)

    assert [c.id for c in categories] == [active.id]


async def test_excludes_an_inactive_category() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id = new_tenant_id()
    inactive = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    inactive.is_active = False
    await uow_factory.categories.add(inactive)
    use_case = ListPublicCategoryChildren(uow_factory)

    categories = await use_case(tenant_id=tenant_id, parent_id=None)

    assert categories == []
