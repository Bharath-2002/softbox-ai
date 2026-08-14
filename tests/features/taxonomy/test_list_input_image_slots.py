from __future__ import annotations

from app.entities.image_slots import InputImageSlot
from app.features.taxonomy.list_input_image_slots import ListInputImageSlots
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_only_slots_the_category_itself_owns() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListInputImageSlots(uow_factory)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    own = InputImageSlot.create(tenant_id, category_id, key="border", label="Border", now=utcnow())
    other = InputImageSlot.create(
        tenant_id, other_category_id, key="panel", label="Panel", now=utcnow()
    )
    await uow_factory.input_image_slots.add(own)
    await uow_factory.input_image_slots.add(other)

    listed = await use_case(tenant_id=tenant_id, category_id=category_id)

    assert [s.id for s in listed] == [own.id]
