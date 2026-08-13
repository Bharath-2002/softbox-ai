"""Tenant isolation for ``input_image_slots`` and ``catalog_image_slots``,
proven through the real ``UnitOfWork`` properties. Same pattern as
``test_variant_axis_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant_with_category(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, Category]:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_id) as uow:
        await uow.categories.add(category)
    return tenant_id, category


async def test_tenant_a_cannot_read_tenant_bs_input_slots(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _category_a = await _make_tenant_with_category(owner_uow)
    tenant_b, category_b = await _make_tenant_with_category(owner_uow)
    slot = InputImageSlot.create(
        tenant_b, category_b.id, key="border_detail", label="Border", now=utcnow()
    )
    async with app_uow(tenant_b) as uow:
        await uow.input_image_slots.add(slot)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.input_image_slots.get(tenant_b, slot.id)

    assert fetched is None


async def test_tenant_a_cannot_create_an_input_slot_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _category_a = await _make_tenant_with_category(owner_uow)
    tenant_b, category_b = await _make_tenant_with_category(owner_uow)
    rogue = InputImageSlot.create(
        tenant_b, category_b.id, key="border_detail", label="Border", now=utcnow()
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.input_image_slots.add(rogue)


async def test_tenant_a_cannot_read_tenant_bs_catalog_slots(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _category_a = await _make_tenant_with_category(owner_uow)
    tenant_b, category_b = await _make_tenant_with_category(owner_uow)
    slot = CatalogImageSlot.create(
        tenant_b,
        category_b.id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=utcnow(),
    )
    async with app_uow(tenant_b) as uow:
        await uow.catalog_image_slots.add(slot)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.catalog_image_slots.get(tenant_b, slot.id)

    assert fetched is None


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, category = await _make_tenant_with_category(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.input_image_slots.add(
            InputImageSlot.create(
                tenant_id, category.id, key="border_detail", label="Border", now=utcnow()
            )
        )
        await uow.catalog_image_slots.add(
            CatalogImageSlot.create(
                tenant_id,
                category.id,
                key="closeup",
                label="Close-up",
                aspect_ratio="4:5",
                target_width=1080,
                target_height=1350,
                now=utcnow(),
            )
        )

    async with owner_uow(None) as uow:
        input_count = await uow.session.execute(text("SELECT count(*) FROM input_image_slots"))
        catalog_count = await uow.session.execute(text("SELECT count(*) FROM catalog_image_slots"))

    assert input_count.scalar_one() == 0
    assert catalog_count.scalar_one() == 0
