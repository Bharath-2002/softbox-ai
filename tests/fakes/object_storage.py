from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.services.ports.object_storage import PresignedUpload
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId


class InMemoryObjectStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def new_storage_key(self, tenant_id: TenantId, *, kind: str, extension: str) -> str:
        return f"tenants/{tenant_id}/{kind}/{uuid4()}.{extension.lstrip('.')}"

    async def presign_put(
        self,
        *,
        storage_key: str,
        content_type: str,
        max_bytes: int,
        now: datetime,
        expires_in: timedelta,
    ) -> PresignedUpload:
        return PresignedUpload(
            url=f"https://fake-object-storage.test/{storage_key}",
            method="PUT",
            headers={"Content-Type": content_type},
            storage_key=storage_key,
            expires_at=now + expires_in,
        )

    async def presign_get(self, storage_key: str, *, now: datetime, expires_in: timedelta) -> str:
        return f"https://fake-object-storage.test/{storage_key}"

    async def read(self, storage_key: str) -> bytes:
        if storage_key not in self._objects:
            raise NotFoundError(f"No object at storage key {storage_key!r}.")
        return self._objects[storage_key]

    async def write(self, storage_key: str, data: bytes) -> None:
        self._objects[storage_key] = data

    async def delete(self, storage_key: str) -> None:
        self._objects.pop(storage_key, None)
