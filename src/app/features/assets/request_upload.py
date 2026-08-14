"""Issues a presigned upload (D17) — the authenticated half of the upload
flow. The unauthenticated half (the browser's PUT, and its verification)
is ``VerifyAndRegisterUpload``, reached through the token this mints, not
through a tenant-bound session.
"""

from __future__ import annotations

from datetime import timedelta

from app.entities.asset import UPLOADABLE_ASSET_KINDS, AssetKind
from app.services.ports.object_storage import ObjectStorage, PresignedUpload
from app.shared.clock import Clock
from app.shared.errors import ValidationError
from app.shared.ids import TenantId, UserId


class RequestUpload:
    def __init__(
        self,
        object_storage: ObjectStorage,
        clock: Clock,
        *,
        max_bytes: int = 20_000_000,
        expires_in: timedelta = timedelta(minutes=15),
    ) -> None:
        self._object_storage = object_storage
        self._clock = clock
        self._max_bytes = max_bytes
        self._expires_in = expires_in

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        kind: AssetKind,
        extension: str,
        content_type: str,
        uploaded_by: UserId,
    ) -> PresignedUpload:
        if kind not in UPLOADABLE_ASSET_KINDS:
            raise ValidationError(f"Kind {kind.value!r} cannot be uploaded directly.")

        storage_key = self._object_storage.new_storage_key(
            tenant_id, kind=kind.value, extension=extension
        )
        return await self._object_storage.presign_put(
            tenant_id=tenant_id,
            storage_key=storage_key,
            kind=kind.value,
            uploaded_by=uploaded_by,
            content_type=content_type,
            max_bytes=self._max_bytes,
            now=self._clock.now(),
            expires_in=self._expires_in,
        )
