"""Tenant isolation for ``attribute_definitions``, proven through the real
``UnitOfWork`` property (``uow.attribute_definitions``). Same pattern as
``test_category_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.category import Category
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


async def test_tenant_a_cannot_read_tenant_bs_attribute_definitions(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _category_a = await _make_tenant_with_category(owner_uow)
    tenant_b, category_b = await _make_tenant_with_category(owner_uow)
    definition = AttributeDefinition.create(
        tenant_b,
        category_b.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )
    async with app_uow(tenant_b) as uow:
        await uow.attribute_definitions.add(definition)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.attribute_definitions.get(tenant_b, definition.id)
        listed = await uow.attribute_definitions.list_for_category(tenant_b, category_b.id)

    assert fetched is None
    assert listed == []


async def test_tenant_a_cannot_create_a_definition_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _category_a = await _make_tenant_with_category(owner_uow)
    tenant_b, category_b = await _make_tenant_with_category(owner_uow)
    definition = AttributeDefinition.create(
        tenant_b,
        category_b.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=utcnow(),
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.attribute_definitions.add(definition)


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, category = await _make_tenant_with_category(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.attribute_definitions.add(
            AttributeDefinition.create(
                tenant_id,
                category.id,
                key="fabric",
                label="Fabric",
                data_type=AttributeDataType.TEXT,
                now=utcnow(),
            )
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(text("SELECT count(*) FROM attribute_definitions"))

    assert result.scalar_one() == 0
