from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.features.taxonomy.attach_input_to_catalog_slot import AttachInputToCatalogSlot
from app.shared.errors import NotFoundError
from app.shared.ids import (
    TenantId,
    new_catalog_image_slot_id,
    new_category_id,
    new_input_image_slot_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_slots(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId
) -> tuple[CatalogImageSlot, InputImageSlot]:
    category_id = new_category_id()
    catalog_slot = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    input_slot = InputImageSlot.create(
        tenant_id, category_id, key="border", label="Border", now=_NOW
    )
    await uow_factory.catalog_image_slots.add(catalog_slot)
    await uow_factory.input_image_slots.add(input_slot)
    return catalog_slot, input_slot


async def test_attaches_an_input_to_a_catalog_slot() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = AttachInputToCatalogSlot(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    catalog_slot, input_slot = await _seed_slots(uow_factory, tenant_id)

    requirement = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=catalog_slot.id,
        input_image_slot_id=input_slot.id,
        role="garment_body",
        prompt_position=0,
        actor_user_id=new_user_id(),
    )

    assert requirement.role == "garment_body"
    stored = await uow_factory.catalog_slot_input_requirements.get(
        tenant_id, catalog_slot.id, input_slot.id
    )
    assert stored is not None


async def test_attaching_to_an_unknown_catalog_slot_is_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = AttachInputToCatalogSlot(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    _catalog_slot, input_slot = await _seed_slots(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            catalog_image_slot_id=new_catalog_image_slot_id(),
            input_image_slot_id=input_slot.id,
            role="garment_body",
            prompt_position=0,
            actor_user_id=new_user_id(),
        )


async def test_attaching_an_unknown_input_slot_is_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = AttachInputToCatalogSlot(uow_factory, FakeClock(_NOW))
    tenant_id = new_tenant_id()
    catalog_slot, _input_slot = await _seed_slots(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            catalog_image_slot_id=catalog_slot.id,
            input_image_slot_id=new_input_image_slot_id(),
            role="garment_body",
            prompt_position=0,
            actor_user_id=new_user_id(),
        )
