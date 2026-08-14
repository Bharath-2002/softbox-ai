from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.create_input_image_slot import CreateInputImageSlot
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_creates_a_slot_owned_by_the_category() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CreateInputImageSlot(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)

    slot = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        key="border_detail",
        label="Border detail",
        actor_user_id=new_user_id(),
    )

    assert slot.category_id == category.id
    stored = await uow_factory.input_image_slots.get(tenant_id, slot.id)
    assert stored is not None and stored.key == "border_detail"


async def test_creating_on_an_unknown_category_is_not_found() -> None:
    use_case = CreateInputImageSlot(FakeUnitOfWorkFactory(), FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            key="border_detail",
            label="Border detail",
            actor_user_id=new_user_id(),
        )
