from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.attribute_definition import AttributeDataType
from app.entities.category import Category
from app.features.taxonomy.create_attribute_definition import CreateAttributeDefinition
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_creates_a_definition_owned_by_the_category() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CreateAttributeDefinition(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)

    definition = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        actor_user_id=new_user_id(),
    )

    assert definition.category_id == category.id
    stored = await uow_factory.attribute_definitions.get(tenant_id, definition.id)
    assert stored is not None and stored.key == "fabric"


async def test_creating_on_an_unknown_category_is_not_found() -> None:
    use_case = CreateAttributeDefinition(FakeUnitOfWorkFactory(), FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            key="fabric",
            label="Fabric",
            data_type=AttributeDataType.TEXT,
            actor_user_id=new_user_id(),
        )
