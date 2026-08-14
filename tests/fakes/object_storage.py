from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from app.services.ports.object_storage import PresignedUpload, UploadClaims
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import TenantId, UserId


@dataclass(frozen=True)
class _PendingPut:
    claims: UploadClaims
    max_bytes: int
    expires_at: datetime


@dataclass(frozen=True)
class _PendingGet:
    storage_key: str
    expires_at: datetime


class InMemoryObjectStorage:
    """No real signing - a ``presign_put``/``presign_get`` token is just an
    opaque id looked up in an in-memory table. Good enough for exercising
    use-case logic against this fake; the token-forgery-resistance property
    is what ``PresignTokenCodec``'s own tests (against the real adapter)
    cover, not this fake.
    """

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}
        self._pending_puts: dict[str, _PendingPut] = {}
        self._pending_gets: dict[str, _PendingGet] = {}

    def new_storage_key(self, tenant_id: TenantId, *, kind: str, extension: str) -> str:
        return f"tenants/{tenant_id}/{kind}/{uuid4()}.{extension.lstrip('.')}"

    async def presign_put(
        self,
        *,
        tenant_id: TenantId,
        storage_key: str,
        kind: str,
        uploaded_by: UserId,
        content_type: str,
        max_bytes: int,
        now: datetime,
        expires_in: timedelta,
    ) -> PresignedUpload:
        token = str(uuid4())
        self._pending_puts[token] = _PendingPut(
            claims=UploadClaims(
                tenant_id=tenant_id, storage_key=storage_key, kind=kind, uploaded_by=uploaded_by
            ),
            max_bytes=max_bytes,
            expires_at=now + expires_in,
        )
        return PresignedUpload(
            url=f"https://fake-object-storage.test/{token}",
            method="PUT",
            headers={"Content-Type": content_type},
            storage_key=storage_key,
            expires_at=now + expires_in,
        )

    async def presign_get(self, storage_key: str, *, now: datetime, expires_in: timedelta) -> str:
        token = str(uuid4())
        self._pending_gets[token] = _PendingGet(
            storage_key=storage_key, expires_at=now + expires_in
        )
        return f"https://fake-object-storage.test/{token}"

    async def accept_upload(self, token: str, data: bytes, *, now: datetime) -> UploadClaims:
        pending = self._pending_puts.get(token)
        if pending is None or now > pending.expires_at:
            raise ValidationError("Invalid or expired upload token.")
        if len(data) > pending.max_bytes:
            raise ValidationError("Upload exceeds the size declared when it was requested.")
        await self.write(pending.claims.storage_key, data)
        return pending.claims

    async def resolve_download(self, token: str, *, now: datetime) -> bytes:
        pending = self._pending_gets.get(token)
        if pending is None or now > pending.expires_at:
            raise ValidationError("Invalid or expired download token.")
        return await self.read(pending.storage_key)

    async def read(self, storage_key: str) -> bytes:
        if storage_key not in self._objects:
            raise NotFoundError(f"No object at storage key {storage_key!r}.")
        return self._objects[storage_key]

    async def write(self, storage_key: str, data: bytes) -> None:
        self._objects[storage_key] = data

    async def delete(self, storage_key: str) -> None:
        self._objects.pop(storage_key, None)
