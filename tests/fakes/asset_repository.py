from __future__ import annotations

from app.entities.asset import Asset, AssetKind
from app.shared.ids import AssetId, TenantId


class InMemoryAssetRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, AssetId], Asset] = {}

    async def get(self, tenant_id: TenantId, asset_id: AssetId) -> Asset | None:
        return self._rows.get((tenant_id, asset_id))

    async def get_by_sha256(
        self, tenant_id: TenantId, sha256: str, kind: AssetKind
    ) -> Asset | None:
        sha256_lower = sha256.lower()
        for (tid, _), row in self._rows.items():
            if tid == tenant_id and row.sha256 == sha256_lower and row.kind == kind:
                return row
        return None

    async def add(self, asset: Asset) -> None:
        self._rows[(asset.tenant_id, asset.id)] = asset
