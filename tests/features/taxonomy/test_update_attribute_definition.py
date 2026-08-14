from __future__ import annotations

import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.features.taxonomy.update_attribute_definition import UpdateAttributeDefinition
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_attribute_definition_id, new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_editable_fields_and_keeps_the_key() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateAttributeDefinition(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    definition = AttributeDefinition.create(
        tenant_id,
        new_category_id(),
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )
    await uow_factory.attribute_definitions.add(definition)

    updated = await use_case(
        tenant_id=tenant_id,
        definition_id=definition.id,
        label="Fabric type",
        help_text="Pick one",
        semantic_role=None,
        is_required=True,
        is_filterable=True,
        is_public=True,
        position=1,
        validation={},
        ui={},
        default_value=None,
        actor_user_id=new_user_id(),
    )

    assert updated.label == "Fabric type"
    assert updated.is_required is True
    assert updated.key == "fabric"


async def test_updating_an_unknown_definition_is_not_found() -> None:
    use_case = UpdateAttributeDefinition(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            definition_id=new_attribute_definition_id(),
            label="X",
            help_text=None,
            semantic_role=None,
            is_required=False,
            is_filterable=False,
            is_public=True,
            position=0,
            validation={},
            ui={},
            default_value=None,
            actor_user_id=new_user_id(),
        )
