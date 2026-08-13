"""Implements
``app.services.ports.tenant_membership_repository.TenantMembershipRepository``.

``tenant_memberships`` carries no RLS (see the migration's module docstring —
it turned out to be a resolver table, like ``sessions``/``tenant_domains``,
for a reason only found by testing the "list every tenant this user belongs
to" query against real RLS and getting zero rows back). Every method below
still filters explicitly by ``tenant_id`` and/or ``user_id`` regardless — a
policy would have caught a missing filter here; without one, the filter is
the only thing that does, so it is never optional.

Filters use ``tenant_memberships_table.c.*``, not the mapped class's own
attributes — see ``user_repository.py`` for why.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.tenant_membership import TenantMembership
from app.infrastructure.persistence.mapping import tenant_memberships_table
from app.shared.ids import TenantId, UserId


class SqlTenantMembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, user_id: UserId) -> TenantMembership | None:
        stmt = select(TenantMembership).where(
            tenant_memberships_table.c.tenant_id == tenant_id,
            tenant_memberships_table.c.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_user(self, user_id: UserId) -> list[TenantMembership]:
        stmt = select(TenantMembership).where(tenant_memberships_table.c.user_id == user_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def add(self, membership: TenantMembership) -> None:
        self._session.add(membership)
        await self._session.flush()
