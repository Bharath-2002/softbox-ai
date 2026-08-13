"""Tenant isolation for ``catalog_slot_input_requirements``, proven through
the real ``UnitOfWork`` property. Same pattern as
``test_image_slots_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant_with_slots(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, CatalogImageSlotId, InputImageSlotId]:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    catalog_slot = CatalogImageSlot.create(
        tenant_id,
        category.id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )
    input_slot = InputImageSlot.create(
        tenant_id, category.id, key="border_detail", label="Border", now=utcnow()
    )
    async with owner_uow(tenant_id) as uow:
        await uow.categories.add(category)
        await uow.catalog_image_slots.add(catalog_slot)
        await uow.input_image_slots.add(input_slot)
    return tenant_id, catalog_slot.id, input_slot.id


async def test_tenant_a_cannot_read_tenant_bs_requirements(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _c, _i = await _make_tenant_with_slots(owner_uow)
    tenant_b, catalog_slot_b, input_slot_b = await _make_tenant_with_slots(owner_uow)
    requirement = CatalogSlotInputRequirement.create(
        tenant_b, catalog_slot_b, input_slot_b, role="garment_body", prompt_position=0, now=utcnow()
    )
    async with app_uow(tenant_b) as uow:
        await uow.catalog_slot_input_requirements.add(requirement)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.catalog_slot_input_requirements.get(
            tenant_b, catalog_slot_b, input_slot_b
        )
        listed = await uow.catalog_slot_input_requirements.list_for_catalog_slot(
            tenant_b, catalog_slot_b
        )

    assert fetched is None
    assert listed == []


async def test_tenant_a_cannot_create_a_requirement_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _c, _i = await _make_tenant_with_slots(owner_uow)
    tenant_b, catalog_slot_b, input_slot_b = await _make_tenant_with_slots(owner_uow)
    rogue = CatalogSlotInputRequirement.create(
        tenant_b, catalog_slot_b, input_slot_b, role="garment_body", prompt_position=0, now=utcnow()
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.catalog_slot_input_requirements.add(rogue)


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, catalog_slot_id, input_slot_id = await _make_tenant_with_slots(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.catalog_slot_input_requirements.add(
            CatalogSlotInputRequirement.create(
                tenant_id,
                catalog_slot_id,
                input_slot_id,
                role="garment_body",
                prompt_position=0,
                now=utcnow(),
            )
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(
            text("SELECT count(*) FROM catalog_slot_input_requirements")
        )

    assert result.scalar_one() == 0
