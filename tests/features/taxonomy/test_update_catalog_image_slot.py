from __future__ import annotations

import pytest

from app.entities.image_slots import CatalogImageSlot
from app.features.taxonomy.update_catalog_image_slot import UpdateCatalogImageSlot
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_catalog_image_slot_id, new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_update_replaces_editable_fields_and_keeps_the_key() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = UpdateCatalogImageSlot(uow_factory, FakeClock(utcnow()))
    tenant_id = new_tenant_id()
    slot = CatalogImageSlot.create(
        tenant_id,
        new_category_id(),
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )
    await uow_factory.catalog_image_slots.add(slot)

    updated = await use_case(
        tenant_id=tenant_id,
        slot_id=slot.id,
        label="Close-up (renamed)",
        description="d",
        aspect_ratio="1:1",
        target_width=1000,
        target_height=1000,
        is_required=False,
        position=1,
        actor_user_id=new_user_id(),
    )

    assert updated.label == "Close-up (renamed)"
    assert updated.aspect_ratio == "1:1"
    assert updated.key == "closeup"


async def test_updating_an_unknown_slot_is_not_found() -> None:
    use_case = UpdateCatalogImageSlot(FakeUnitOfWorkFactory(), FakeClock(utcnow()))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            slot_id=new_catalog_image_slot_id(),
            label="X",
            description=None,
            aspect_ratio="4:5",
            target_width=1080,
            target_height=1350,
            is_required=True,
            position=0,
            actor_user_id=new_user_id(),
        )
