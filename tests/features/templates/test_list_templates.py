from __future__ import annotations

from datetime import UTC, datetime

from app.entities.catalog_template import CatalogTemplate
from app.entities.image_slots import CatalogImageSlot
from app.features.templates.list_templates import ListTemplates
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_lists_only_templates_for_the_given_catalog_slot() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ListTemplates(uow_factory)
    tenant_id = new_tenant_id()
    slot = CatalogImageSlot.create(
        tenant_id,
        new_category_id(),
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    other_slot = CatalogImageSlot.create(
        tenant_id,
        new_category_id(),
        key="worn",
        label="Worn",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    await uow_factory.catalog_image_slots.add(slot)
    await uow_factory.catalog_image_slots.add(other_slot)
    own = CatalogTemplate.create_authored(
        tenant_id, slot.id, name="a", prompt_template="x", created_by=new_user_id(), now=_NOW
    )
    other = CatalogTemplate.create_authored(
        tenant_id, other_slot.id, name="b", prompt_template="x", created_by=new_user_id(), now=_NOW
    )
    await uow_factory.catalog_templates.add(own)
    await uow_factory.catalog_templates.add(other)

    listed = await use_case(tenant_id=tenant_id, catalog_image_slot_id=slot.id)

    assert [t.id for t in listed] == [own.id]
