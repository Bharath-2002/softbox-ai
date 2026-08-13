"""Tenant isolation for ``category_spec_versions``, proven through the real
``UnitOfWork`` property. Same pattern as
``test_catalog_slot_input_requirement_isolation.py``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import CategoryId, TenantId, UserId, new_tenant_id, new_user_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
_INSERT_USER = text(
    "INSERT INTO users (id, email, email_verified, status, created_at, updated_at) "
    "VALUES (:id, :email, true, 'active', now(), now())"
)


async def _make_tenant_with_category_and_user(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, CategoryId, UserId]:
    tenant_id = new_tenant_id()
    user_id = new_user_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
        await uow.session.execute(
            _INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_id) as uow:
        await uow.categories.add(category)
    return tenant_id, category.id, user_id


async def test_tenant_a_cannot_read_tenant_bs_spec_versions(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _cat_a, _user_a = await _make_tenant_with_category_and_user(owner_uow)
    tenant_b, category_b, user_b = await _make_tenant_with_category_and_user(owner_uow)
    version = CategorySpecVersion.create(
        tenant_b, category_b, version=1, snapshot={}, published_by=user_b, now=utcnow()
    )
    async with app_uow(tenant_b) as uow:
        await uow.category_spec_versions.add(version)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.category_spec_versions.get(tenant_b, version.id)
        listed = await uow.category_spec_versions.list_for_category(tenant_b, category_b)

    assert fetched is None
    assert listed == []


async def test_tenant_a_cannot_create_a_spec_version_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a, _cat_a, _user_a = await _make_tenant_with_category_and_user(owner_uow)
    tenant_b, category_b, user_b = await _make_tenant_with_category_and_user(owner_uow)
    rogue = CategorySpecVersion.create(
        tenant_b, category_b, version=1, snapshot={}, published_by=user_b, now=utcnow()
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.category_spec_versions.add(rogue)


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id, category_id, user_id = await _make_tenant_with_category_and_user(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.category_spec_versions.add(
            CategorySpecVersion.create(
                tenant_id, category_id, version=1, snapshot={}, published_by=user_id, now=utcnow()
            )
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(text("SELECT count(*) FROM category_spec_versions"))

    assert result.scalar_one() == 0
