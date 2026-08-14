"""Implements ``app.services.ports.tenant_repository.TenantRepository``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import tenants_table
from app.shared.ids import TenantId


class SqlTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[TenantId]:
        stmt = select(tenants_table.c.id).where(tenants_table.c.status == "active")
        return list((await self._session.execute(stmt)).scalars().all())
