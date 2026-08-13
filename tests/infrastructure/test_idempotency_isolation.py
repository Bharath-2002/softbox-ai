"""Tenant isolation for ``idempotency_keys``, proven through the real
``UnitOfWork`` property (``uow.idempotency_keys``) — the shape every real
caller will use — rather than a bare repository against a manually-bound
session (see ``tests/services/test_idempotency_repository_contract.py`` for
the single-tenant operation contract).

``reserve()``'s ``ON CONFLICT`` targets a composite ``(tenant_id, key)``
unique index, not a plain ``key`` uniqueness constraint — worth confirming
directly that two tenants really can use the identical key string without
colliding, the same "seed both, then assert" discipline
``test_tenant_isolation.py`` uses for ``audit_log``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

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


async def test_the_same_key_is_independent_per_tenant(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)

    async with app_uow(tenant_a) as uow:
        claimed_a = await uow.idempotency_keys.reserve(
            tenant_a, "shared-key", request_fingerprint="fp", now=utcnow()
        )
    async with app_uow(tenant_b) as uow:
        claimed_b = await uow.idempotency_keys.reserve(
            tenant_b, "shared-key", request_fingerprint="fp", now=utcnow()
        )

    assert claimed_a is True
    assert claimed_b is True


async def test_app_role_with_no_tenant_bound_cannot_see_a_reserved_key(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """Fails closed: reserving under a bound tenant does not leak into a
    query run with no tenant bound at all."""
    tenant_id = await _make_tenant(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.idempotency_keys.reserve(
            tenant_id, "op-1", request_fingerprint="fp", now=utcnow()
        )

    async with app_uow(None) as uow:
        record = await uow.idempotency_keys.get(tenant_id, "op-1")

    assert record is None


async def test_tenant_a_cannot_reserve_a_key_tagged_as_tenant_b(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """WITH CHECK, not just USING: a session bound to tenant A is rejected
    even if the caller explicitly passes tenant B's id to reserve()."""
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.idempotency_keys.reserve(
                tenant_b, "op-2", request_fingerprint="fp", now=utcnow()
            )


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    async with app_uow(tenant_id) as uow:
        await uow.idempotency_keys.reserve(
            tenant_id, "op-3", request_fingerprint="fp", now=utcnow()
        )

    async with owner_uow(None) as uow:
        result = await uow.session.execute(text("SELECT count(*) FROM idempotency_keys"))

    assert result.scalar_one() == 0
