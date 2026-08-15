"""Implements
``app.services.ports.tenant_domain_repository.TenantDomainRepository``.

``tenant_domains`` carries no RLS (see the migration's module docstring) —
every method filters explicitly, including ``resolve_by_hostname``, which
filters only by ``hostname`` because no tenant is known yet; that is its
entire purpose.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.tenant_domain import TenantDomain
from app.infrastructure.persistence.mapping import tenant_domains_table
from app.shared.ids import TenantDomainId, TenantId


class SqlTenantDomainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_by_hostname(self, hostname: str) -> TenantDomain | None:
        stmt = select(TenantDomain).where(tenant_domains_table.c.hostname == hostname)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get(self, tenant_id: TenantId, domain_id: TenantDomainId) -> TenantDomain | None:
        stmt = select(TenantDomain).where(
            tenant_domains_table.c.tenant_id == tenant_id,
            tenant_domains_table.c.id == domain_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(self, tenant_id: TenantId) -> list[TenantDomain]:
        stmt = (
            select(TenantDomain)
            .where(tenant_domains_table.c.tenant_id == tenant_id)
            .order_by(tenant_domains_table.c.created_at)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def add(self, domain: TenantDomain) -> None:
        self._session.add(domain)
        await self._session.flush()
