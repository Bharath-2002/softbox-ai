"""Implements ``app.services.ports.asset_repository.AssetRepository``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.asset import Asset, AssetKind
from app.infrastructure.persistence.mapping import assets_table
from app.shared.ids import AssetId, TenantId


class SqlAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, asset_id: AssetId) -> Asset | None:
        stmt = select(Asset).where(
            assets_table.c.tenant_id == tenant_id, assets_table.c.id == asset_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_sha256(
        self, tenant_id: TenantId, sha256: str, kind: AssetKind
    ) -> Asset | None:
        stmt = select(Asset).where(
            assets_table.c.tenant_id == tenant_id,
            assets_table.c.sha256 == sha256.lower(),
            assets_table.c.kind == kind,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, asset: Asset) -> None:
        self._session.add(asset)
        await self._session.flush()
