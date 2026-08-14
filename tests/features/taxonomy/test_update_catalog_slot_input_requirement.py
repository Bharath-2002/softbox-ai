from __future__ import annotations

import pytest

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.features.taxonomy.update_catalog_slot_input_requirement import (
    UpdateCatalogSlotInputRequirement,
)
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_input_image_slot_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_role_and_prompt_position() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateCatalogSlotInputRequirement(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    catalog_slot_id = new_catalog_image_slot_id()
    input_slot_id = new_input_image_slot_id()
    requirement = CatalogSlotInputRequirement.create(
        tenant_id,
        catalog_slot_id,
        input_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await uow_factory.catalog_slot_input_requirements.add(requirement)

    updated = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=catalog_slot_id,
        input_image_slot_id=input_slot_id,
        role="border_detail",
        prompt_position=1,
        is_required=False,
        actor_user_id=new_user_id(),
    )

    assert updated.role == "border_detail"
    assert updated.prompt_position == 1
    assert updated.is_required is False


async def test_updating_an_unknown_pairing_is_not_found() -> None:
    use_case = UpdateCatalogSlotInputRequirement(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            catalog_image_slot_id=new_catalog_image_slot_id(),
            input_image_slot_id=new_input_image_slot_id(),
            role="x",
            prompt_position=0,
            is_required=True,
            actor_user_id=new_user_id(),
        )
