from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.features.taxonomy.detach_input_from_catalog_slot import DetachInputFromCatalogSlot
from app.shared.clock import utcnow
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_input_image_slot_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_detach_removes_the_pairing() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = DetachInputFromCatalogSlot(uow_factory, FakeClock(utcnow()))
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

    await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=catalog_slot_id,
        input_image_slot_id=input_slot_id,
        actor_user_id=new_user_id(),
    )

    assert (
        await uow_factory.catalog_slot_input_requirements.get(
            tenant_id, catalog_slot_id, input_slot_id
        )
        is None
    )


async def test_detach_is_idempotent_on_an_unknown_pairing() -> None:
    use_case = DetachInputFromCatalogSlot(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    await use_case(
        tenant_id=new_tenant_id(),
        catalog_image_slot_id=new_catalog_image_slot_id(),
        input_image_slot_id=new_input_image_slot_id(),
        actor_user_id=new_user_id(),
    )
