from __future__ import annotations

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.features.taxonomy.list_attribute_definitions import ListAttributeDefinitions
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_only_definitions_the_category_itself_owns() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListAttributeDefinitions(uow_factory)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    own = AttributeDefinition.create(
        tenant_id,
        category_id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )
    other = AttributeDefinition.create(
        tenant_id,
        other_category_id,
        key="colour",
        label="Colour",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )
    await uow_factory.attribute_definitions.add(own)
    await uow_factory.attribute_definitions.add(other)

    listed = await use_case(tenant_id=tenant_id, category_id=category_id)

    assert [d.id for d in listed] == [own.id]
