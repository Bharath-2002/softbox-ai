"""The "verification callback" D17 describes: turns a batch of bytes already
sitting in object storage (via a presigned PUT) into a recorded ``Asset``
row — or rejects them and removes the bytes. Only ``template`` and
``input`` kinds go through here; ``generated`` and ``derivative`` assets are
written directly by internal pipeline code (M5/M6), never by a browser
upload.

Order of checks is cheapest-and-most-conclusive first: size (a single
``len()``), then whether the bytes are even a real, readable image of an
allowed format (catches an extension lie for free), then dimensions, then
the moderation scan (the one that would cost money against a real
provider). A rejection at any step deletes the uploaded bytes rather than
leaving them sitting in storage.
"""

from __future__ import annotations

import hashlib

from app.entities.asset import UPLOADABLE_ASSET_KINDS, Asset, AssetKind
from app.services.image_inspection import inspect_image
from app.services.ports.content_moderation import ContentModerationScanner
from app.services.ports.object_storage import ObjectStorage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import ValidationError
from app.shared.ids import TenantId, UserId


class VerifyAndRegisterUpload:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        object_storage: ObjectStorage,
        moderation_scanner: ContentModerationScanner,
        clock: Clock,
        *,
        max_bytes: int = 20_000_000,
        max_dimension: int = 8000,
    ) -> None:
        self._uow_factory = uow_factory
        self._object_storage = object_storage
        self._moderation_scanner = moderation_scanner
        self._clock = clock
        self._max_bytes = max_bytes
        self._max_dimension = max_dimension

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        storage_key: str,
        kind: AssetKind,
        uploaded_by: UserId,
    ) -> Asset:
        if kind not in UPLOADABLE_ASSET_KINDS:
            raise ValidationError(f"Kind {kind.value!r} cannot be uploaded directly.")

        data = await self._object_storage.read(storage_key)

        if len(data) > self._max_bytes:
            await self._object_storage.delete(storage_key)
            raise ValidationError("Upload exceeds the maximum allowed size.")

        try:
            inspection = inspect_image(data)
        except ValidationError:
            await self._object_storage.delete(storage_key)
            raise

        if inspection.width > self._max_dimension or inspection.height > self._max_dimension:
            await self._object_storage.delete(storage_key)
            raise ValidationError("Image dimensions exceed the maximum allowed.")

        verdict = await self._moderation_scanner.scan(data, mime=inspection.mime)
        if not verdict.is_safe:
            await self._object_storage.delete(storage_key)
            raise ValidationError(f"Upload rejected by content moderation: {verdict.reason}")

        sha256 = hashlib.sha256(data).hexdigest()
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            existing = await uow.assets.get_by_sha256(tenant_id, sha256, kind)
            if existing is not None:
                # Dedup (D17): the same bytes already have a row - discard
                # this upload's copy rather than leaving it orphaned in
                # storage with nothing ever pointing at it.
                await self._object_storage.delete(storage_key)
                return existing

            asset = Asset.create(
                tenant_id,
                storage_key=storage_key,
                sha256=sha256,
                mime=inspection.mime,
                width=inspection.width,
                height=inspection.height,
                bytes_=len(data),
                kind=kind,
                source="upload",
                now=now,
                uploaded_by=uploaded_by,
            )
            await uow.assets.add(asset)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=uploaded_by,
                action="asset.uploaded",
                subject_type="asset",
                subject_id=asset.id,
                before=None,
                after={"kind": kind.value, "sha256": sha256},
                now=now,
            )

            return asset
