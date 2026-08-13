"""Tenant isolation for ``categories``, proven through the real
``UnitOfWork`` property (``uow.categories``) — the shape every real caller
will use. Same pattern as ``test_audit_log_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.category import Category
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant(owner_uow: Callable[[TenantId | None], SqlUnitOfWork]) -> TenantId:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    return tenant_id


async def test_app_role_with_no_tenant_bound_sees_no_categories(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with app_uow(tenant_id) as uow:
        await uow.categories.add(category)

    async with app_uow(None) as uow:
        fetched = await uow.categories.get(tenant_id, category.id)

    assert fetched is None


async def test_tenant_a_cannot_read_tenant_bs_categories(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    category = Category.create(
        tenant_b, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with app_uow(tenant_b) as uow:
        await uow.categories.add(category)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.categories.get(tenant_b, category.id)
        children = await uow.categories.list_children(tenant_b, None)

    assert fetched is None
    assert children == []


async def test_tenant_a_cannot_create_a_category_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """WITH CHECK, not just USING - a session bound to tenant A is rejected
    even when it explicitly builds a row tagged as tenant B."""
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    category = Category.create(
        tenant_b, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.categories.add(category)


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.categories.add(
            Category.create(
                tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
            )
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(text("SELECT count(*) FROM categories"))

    assert result.scalar_one() == 0
