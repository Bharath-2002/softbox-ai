"""Asset storage (D17). ``get_by_sha256`` is what the upload-verification
use case calls before inserting, so the same bytes reused for the same
``kind`` returns the existing row instead of racing the unique constraint —
the constraint is the correctness guard against concurrent duplicate
inserts, this lookup is what makes the common case a clean no-op rather than
a caught ``IntegrityError``.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.asset import Asset, AssetKind
from app.shared.ids import AssetId, TenantId


class AssetRepository(Protocol):
    async def get(self, tenant_id: TenantId, asset_id: AssetId) -> Asset | None: ...

    async def get_by_sha256(
        self, tenant_id: TenantId, sha256: str, kind: AssetKind
    ) -> Asset | None: ...

    async def add(self, asset: Asset) -> None: ...
