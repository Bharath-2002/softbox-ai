from __future__ import annotations

from app.entities.image_slots import CatalogImageSlot
from app.features.taxonomy.list_catalog_image_slots import ListCatalogImageSlots
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_only_slots_the_category_itself_owns() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListCatalogImageSlots(uow_factory)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    other_category_id = new_category_id()
    own = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )
    other = CatalogImageSlot.create(
        tenant_id,
        other_category_id,
        key="wide",
        label="Wide",
        aspect_ratio="16:9",
        target_width=1920,
        target_height=1080,
        now=utcnow(),
    )
    await uow_factory.catalog_image_slots.add(own)
    await uow_factory.catalog_image_slots.add(other)

    listed = await use_case(tenant_id=tenant_id, category_id=category_id)

    assert [s.id for s in listed] == [own.id]
