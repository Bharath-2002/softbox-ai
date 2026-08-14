from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.features.taxonomy.list_catalog_slot_input_requirements import (
    ListCatalogSlotInputRequirements,
)
from app.shared.clock import utcnow
from app.shared.ids import new_catalog_image_slot_id, new_input_image_slot_id, new_tenant_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_lists_requirements_ordered_by_prompt_position() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListCatalogSlotInputRequirements(uow_factory)
    tenant_id = new_tenant_id()
    catalog_slot_id = new_catalog_image_slot_id()
    second = CatalogSlotInputRequirement.create(
        tenant_id,
        catalog_slot_id,
        new_input_image_slot_id(),
        role="border_detail",
        prompt_position=1,
        now=utcnow(),
    )
    first = CatalogSlotInputRequirement.create(
        tenant_id,
        catalog_slot_id,
        new_input_image_slot_id(),
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await uow_factory.catalog_slot_input_requirements.add(second)
    await uow_factory.catalog_slot_input_requirements.add(first)

    listed = await use_case(tenant_id=tenant_id, catalog_image_slot_id=catalog_slot_id)

    assert [r.role for r in listed] == ["garment_body", "border_detail"]
