from __future__ import annotations

import pytest

from app.entities.image_slots import InputImageSlot
from app.features.taxonomy.update_input_image_slot import UpdateInputImageSlot
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_input_image_slot_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_editable_fields_and_keeps_the_key() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateInputImageSlot(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    slot = InputImageSlot.create(
        tenant_id, new_category_id(), key="border_detail", label="Border", now=utcnow()
    )
    await uow_factory.input_image_slots.add(slot)

    updated = await use_case(
        tenant_id=tenant_id,
        slot_id=slot.id,
        label="Border detail (renamed)",
        description="d",
        capture_guidance="g",
        example_asset_id=None,
        normalisation={},
        is_required=False,
        position=1,
        actor_user_id=new_user_id(),
    )

    assert updated.label == "Border detail (renamed)"
    assert updated.is_required is False
    assert updated.key == "border_detail"


async def test_updating_an_unknown_slot_is_not_found() -> None:
    use_case = UpdateInputImageSlot(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            slot_id=new_input_image_slot_id(),
            label="X",
            description=None,
            capture_guidance=None,
            example_asset_id=None,
            normalisation={},
            is_required=True,
            position=0,
            actor_user_id=new_user_id(),
        )
