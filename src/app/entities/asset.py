"""Content-addressed assets (D17). The API records a row here only *after*
a presigned direct upload to object storage has been verified — this entity
models the post-verification record, not an in-progress upload. There is no
"pending" status to represent, the same reasoning ``category_spec_versions``
uses for having no ``draft`` row: a row only ever exists because a
verification callback just confirmed real, safe bytes are sitting in
storage at ``storage_key``.

``UNIQUE (tenant_id, sha256, kind)`` is the dedup guard (D17) — the same
photograph attached as an ``input`` twice collapses to one row; the same
bytes reused as a ``template`` is a distinct row, since the two kinds are
different uses of the content and each carries its own lifecycle.

``parent_asset_id`` is nullable and self-referencing, for per-channel
derivative renditions (D17) generated at publish time from an approved
master — not populated by anything in M3, but part of the base shape so a
later milestone does not need to alter this table.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.errors import ValidationError
from app.shared.ids import AssetId, TenantId, UserId, new_asset_id


class AssetKind(StrEnum):
    TEMPLATE = "template"
    INPUT = "input"
    GENERATED = "generated"
    DERIVATIVE = "derivative"


@dataclass
class Asset:
    id: AssetId
    tenant_id: TenantId
    storage_key: str
    sha256: str
    mime: str
    width: int
    height: int
    bytes: int
    kind: AssetKind
    source: str
    parent_asset_id: AssetId | None
    meta: dict[str, Any]
    uploaded_by: UserId | None
    created_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        *,
        storage_key: str,
        sha256: str,
        mime: str,
        width: int,
        height: int,
        bytes_: int,
        kind: AssetKind,
        source: str,
        now: datetime,
        parent_asset_id: AssetId | None = None,
        meta: dict[str, Any] | None = None,
        uploaded_by: UserId | None = None,
    ) -> Asset:
        sha256_lower = sha256.lower()
        if len(sha256_lower) != 64 or any(c not in "0123456789abcdef" for c in sha256_lower):
            raise ValidationError("sha256 must be 64 hex characters")
        if width <= 0 or height <= 0:
            raise ValidationError("width and height must be positive")
        if bytes_ <= 0:
            raise ValidationError("bytes must be positive")
        return Asset(
            id=new_asset_id(),
            tenant_id=tenant_id,
            storage_key=storage_key,
            sha256=sha256_lower,
            mime=mime,
            width=width,
            height=height,
            bytes=bytes_,
            kind=kind,
            source=source,
            parent_asset_id=parent_asset_id,
            meta=meta or {},
            uploaded_by=uploaded_by,
            created_at=now,
        )
