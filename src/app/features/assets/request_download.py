"""Issues a presigned download URL (D17, CLAUDE.md §11 "private assets
served by signed short-lived URLs") — the authenticated half of the
download flow, mirroring ``RequestUpload``. The unauthenticated half (the
browser's GET) lands on ``webhooks.py``'s download route, reached through
the token this mints, not through a tenant-bound session.
"""

from __future__ import annotations

from datetime import timedelta

from app.services.ports.object_storage import ObjectStorage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import AssetId, TenantId


class RequestDownload:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        object_storage: ObjectStorage,
        clock: Clock,
        *,
        expires_in: timedelta = timedelta(minutes=15),
    ) -> None:
        self._uow_factory = uow_factory
        self._object_storage = object_storage
        self._clock = clock
        self._expires_in = expires_in

    async def __call__(self, *, tenant_id: TenantId, asset_id: AssetId) -> str:
        async with self._uow_factory(tenant_id) as uow:
            asset = await uow.assets.get(tenant_id, asset_id)
            if asset is None:
                raise NotFoundError("Asset not found.")

        return await self._object_storage.presign_get(
            asset.storage_key,
            content_type=asset.mime,
            now=self._clock.now(),
            expires_in=self._expires_in,
        )
