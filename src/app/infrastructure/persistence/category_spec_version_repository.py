"""Implements
``app.services.ports.category_spec_version_repository.CategorySpecVersionRepository``.

No ``update`` — see the port's docstring for why that omission is load-bearing,
not an oversight.
"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.category_spec_version import CategorySpecVersion
from app.infrastructure.persistence.mapping import category_spec_versions_table
from app.shared.ids import CategoryId, CategorySpecVersionId, TenantId


class SqlCategorySpecVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, version_id: CategorySpecVersionId
    ) -> CategorySpecVersion | None:
        stmt = select(CategorySpecVersion).where(
            category_spec_versions_table.c.tenant_id == tenant_id,
            category_spec_versions_table.c.id == version_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_version(
        self, tenant_id: TenantId, category_id: CategoryId, version: int
    ) -> CategorySpecVersion | None:
        stmt = select(CategorySpecVersion).where(
            category_spec_versions_table.c.tenant_id == tenant_id,
            category_spec_versions_table.c.category_id == category_id,
            category_spec_versions_table.c.version == version,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, version: CategorySpecVersion) -> None:
        self._session.add(version)
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CategorySpecVersion]:
        stmt = (
            select(CategorySpecVersion)
            .where(
                category_spec_versions_table.c.tenant_id == tenant_id,
                category_spec_versions_table.c.category_id == category_id,
            )
            .order_by(desc(category_spec_versions_table.c.version))
        )
        return list((await self._session.execute(stmt)).scalars().all())
