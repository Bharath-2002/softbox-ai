from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.create_variant_axis import CreateVariantAxis
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_creates_an_axis_owned_by_the_category() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CreateVariantAxis(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)

    axis = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        key="colour",
        label="Colour",
        affects_imagery=True,
        actor_user_id=new_user_id(),
    )

    assert axis.category_id == category.id
    stored = await uow_factory.variant_axes.get(tenant_id, axis.id)
    assert stored is not None and stored.affects_imagery is True


async def test_creating_on_an_unknown_category_is_not_found() -> None:
    use_case = CreateVariantAxis(FakeUnitOfWorkFactory(), FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            key="colour",
            label="Colour",
            affects_imagery=True,
            actor_user_id=new_user_id(),
        )
