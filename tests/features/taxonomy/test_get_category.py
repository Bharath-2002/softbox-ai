from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.get_category import GetCategory
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_returns_the_category() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = GetCategory(uow_factory)
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id,
        key="apparel",
        name="Apparel",
        slug="apparel",
        parent=None,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await uow_factory.categories.add(category)

    fetched = await use_case(tenant_id=tenant_id, category_id=category.id)

    assert fetched.id == category.id


async def test_unknown_category_is_not_found() -> None:
    use_case = GetCategory(FakeUnitOfWorkFactory())

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), category_id=new_category_id())
