"""Tenant isolation for ``audit_log``, proven through the real
``UnitOfWork`` property (``uow.audit_log``) — the shape every real caller
will use. ``test_tenant_isolation.py`` already proves the RLS mechanism
generically against this exact table via raw SQL (chunk 3); this file
proves the same guarantee holds through the repository built on top of it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.ids import TenantId, new_tenant_id, new_user_id

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


async def test_app_role_with_no_tenant_bound_sees_no_entries(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    subject_id = uuid4()
    async with app_uow(tenant_id) as uow:
        await uow.audit_log.record(
            tenant_id,
            actor_user_id=new_user_id(),
            action="product.updated",
            subject_type="product",
            subject_id=subject_id,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

    async with app_uow(None) as uow:
        entries = await uow.audit_log.list_for_subject(tenant_id, "product", subject_id)

    assert entries == []


async def test_tenant_a_cannot_read_tenant_bs_entries(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    subject_id = uuid4()
    async with app_uow(tenant_b) as uow:
        await uow.audit_log.record(
            tenant_b,
            actor_user_id=new_user_id(),
            action="product.updated",
            subject_type="product",
            subject_id=subject_id,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

    async with app_uow(tenant_a) as uow:
        entries = await uow.audit_log.list_for_subject(tenant_b, "product", subject_id)

    assert entries == []


async def test_tenant_a_cannot_record_an_entry_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """WITH CHECK, not just USING - a session bound to tenant A is rejected
    even when it explicitly passes tenant B's id to record()."""
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.audit_log.record(
                tenant_b,
                actor_user_id=new_user_id(),
                action="product.updated",
                subject_type="product",
                subject_id=uuid4(),
                now=datetime(2026, 1, 1, tzinfo=UTC),
            )


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.audit_log.record(
            tenant_id,
            actor_user_id=new_user_id(),
            action="product.updated",
            subject_type="product",
            subject_id=uuid4(),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(text("SELECT count(*) FROM audit_log"))

    assert result.scalar_one() == 0
