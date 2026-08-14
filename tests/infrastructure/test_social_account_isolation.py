"""Tenant isolation for `social_accounts` (D21/D22) — this table will hold
OAuth credentials once the connect flow lands, so a cross-tenant read here
is the worst leak this schema could produce. Proven through the real
`UnitOfWork` property, same pattern `test_settings_isolation.py` already
established: seed a row for tenant B, then prove tenant A gets `None` for
its id rather than relying on an empty table to pass vacuously (CLAUDE.md
§10).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text

from app.entities.social_account import SocialAccount
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


async def test_tenant_a_cannot_read_tenant_bs_social_account(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    account = SocialAccount.create(
        tenant_b,
        provider="instagram",
        external_account_id="ig-123",
        display_name="The Saree Studio",
        now=utcnow(),
    )
    async with app_uow(tenant_b) as uow:
        await uow.social_accounts.add(account)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.social_accounts.get(tenant_b, account.id)

    assert fetched is None
