"""Tenant isolation for ``variant_axes`` and ``variant_axis_values``, proven
through the real ``UnitOfWork`` properties. Same pattern as
``test_attribute_definition_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.category import Category
from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant_with_axis(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, VariantAxis]:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    axis = VariantAxis.create(
        tenant_id, category.id, key="colour", label="Colour", affects_imagery=True, now=utcnow()
    )
    async with owner_uow(tenant_id) as uow:
        await uow.categories.add(category)
        await uow.variant_axes.add(axis)
    return tenant_id, axis


async def test_tenant_a_cannot_read_tenant_bs_variant_axes(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _axis_a = await _make_tenant_with_axis(owner_uow)
    tenant_b, axis_b = await _make_tenant_with_axis(owner_uow)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.variant_axes.get(tenant_b, axis_b.id)

    assert fetched is None


async def test_tenant_a_cannot_create_an_axis_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _axis_a = await _make_tenant_with_axis(owner_uow)
    tenant_b, axis_b = await _make_tenant_with_axis(owner_uow)
    rogue = VariantAxis.create(
        tenant_b, axis_b.category_id, key="size", label="Size", affects_imagery=False, now=utcnow()
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.variant_axes.add(rogue)


async def test_tenant_a_cannot_read_tenant_bs_axis_values(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _axis_a = await _make_tenant_with_axis(owner_uow)
    tenant_b, axis_b = await _make_tenant_with_axis(owner_uow)
    value = VariantAxisValue.create(
        tenant_b, axis_b.id, value="maroon", label="Maroon", now=utcnow()
    )
    async with app_uow(tenant_b) as uow:
        await uow.variant_axis_values.add(value)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.variant_axis_values.get(tenant_b, value.id)
        listed = await uow.variant_axis_values.list_for_axis(tenant_b, axis_b.id)

    assert fetched is None
    assert listed == []


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, axis = await _make_tenant_with_axis(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.variant_axis_values.add(
            VariantAxisValue.create(
                tenant_id, axis.id, value="maroon", label="Maroon", now=utcnow()
            )
        )

    async with owner_uow(None) as uow:
        axes_count = await uow.session.execute(text("SELECT count(*) FROM variant_axes"))
        values_count = await uow.session.execute(text("SELECT count(*) FROM variant_axis_values"))

    assert axes_count.scalar_one() == 0
    assert values_count.scalar_one() == 0
