"""Implements ``ObjectStorage`` against the local filesystem — the dev/test
stand-in until real object storage credentials exist (see the port's module
docstring).

There is no separate storage *service* to presign a URL against locally, so
the "presigned URL" this adapter hands back points at this same process's
own upload/download routes (``api/routers/webhooks.py`` — see
``docs/ARCHITECTURE.md``'s §8 router table, which already designates
``/api/v1/webhooks/*`` for "upload verification"), carrying a signed,
short-lived JWT that embeds the storage key, the allowed content type and
size cap, and a purpose (``put``/``get``) — verified by that route before
it touches the filesystem, exactly as an S3 presigned URL's signature is
verified by S3 before it touches the bucket. The signing key is deliberately
separate from ``access_token_signing_key`` (a leaked upload token must not
double as a session token, and vice versa).

``joserfc`` (already a transitive dependency via ``authlib``, and already
used directly by ``AccessTokenCodec``) is reused rather than hand-rolling a
second HMAC scheme.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from joserfc import jwt
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry

from app.services.ports.object_storage import DownloadedObject, PresignedUpload, UploadClaims
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import TenantId, UserId

_ALGORITHM = "HS256"
_ISSUER = "softbox-ai-local-object-storage"


class PresignTokenCodec:
    """The signature-is-the-auth mechanism behind a local presigned URL.
    Split out from ``LocalObjectStorage`` so the upload/download route can
    verify a token without depending on the filesystem half of the adapter.
    """

    def __init__(self, signing_key: str) -> None:
        if len(signing_key) < 32:
            raise ValueError("Object storage signing key must be at least 32 characters.")
        self._key = OctKey.import_key(signing_key)

    def encode(
        self,
        *,
        storage_key: str,
        purpose: str,
        now: datetime,
        expires_in: timedelta,
        content_type: str | None = None,
        max_bytes: int | None = None,
        tenant_id: str | None = None,
        kind: str | None = None,
        uploaded_by: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "storage_key": storage_key,
            "purpose": purpose,
            "iss": _ISSUER,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_in).timestamp()),
        }
        if content_type is not None:
            payload["content_type"] = content_type
        if max_bytes is not None:
            payload["max_bytes"] = max_bytes
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        if kind is not None:
            payload["kind"] = kind
        if uploaded_by is not None:
            payload["uploaded_by"] = uploaded_by
        return jwt.encode({"alg": _ALGORITHM}, payload, self._key)

    def decode(self, token: str, *, purpose: str, now: datetime) -> dict[str, Any]:
        try:
            decoded = jwt.decode(token, self._key, algorithms=[_ALGORITHM])
            registry = JWTClaimsRegistry(
                now=int(now.timestamp()),
                exp={"essential": True},
                iss={"essential": True, "value": _ISSUER},
            )
            registry.validate(decoded.claims)
        except Exception as exc:
            raise ValidationError("Invalid or expired upload token.") from exc

        claims = decoded.claims
        if claims.get("purpose") != purpose:
            raise ValidationError("Upload token is not valid for this operation.")
        return dict(claims)


class LocalObjectStorage:
    def __init__(self, *, root: str, base_url: str, signing_key: str) -> None:
        self._root = Path(root)
        self._base_url = base_url.rstrip("/")
        self._tokens = PresignTokenCodec(signing_key)

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
        token = self._tokens.encode(
            storage_key=storage_key,
            purpose="put",
            now=now,
            expires_in=expires_in,
            content_type=content_type,
            max_bytes=max_bytes,
            tenant_id=str(tenant_id),
            kind=kind,
            uploaded_by=str(uploaded_by),
        )
        return PresignedUpload(
            url=f"{self._base_url}/api/v1/webhooks/uploads/{token}",
            method="PUT",
            headers={"Content-Type": content_type},
            storage_key=storage_key,
            expires_at=now + expires_in,
        )

    async def presign_get(
        self, storage_key: str, *, content_type: str, now: datetime, expires_in: timedelta
    ) -> str:
        token = self._tokens.encode(
            storage_key=storage_key,
            purpose="get",
            now=now,
            expires_in=expires_in,
            content_type=content_type,
        )
        return f"{self._base_url}/api/v1/webhooks/uploads/{token}"

    async def peek_upload(self, token: str, *, now: datetime) -> tuple[UploadClaims, int]:
        claims = self._tokens.decode(token, purpose="put", now=now)
        return self._claims_from(claims), int(claims.get("max_bytes", 0))

    async def accept_upload(self, token: str, data: bytes, *, now: datetime) -> UploadClaims:
        claims = self._tokens.decode(token, purpose="put", now=now)
        max_bytes = claims.get("max_bytes")
        if max_bytes is not None and len(data) > max_bytes:
            raise ValidationError("Upload exceeds the size declared when it was requested.")

        upload_claims = self._claims_from(claims)
        await self.write(upload_claims.storage_key, data)
        return upload_claims

    @staticmethod
    def _claims_from(claims: dict[str, Any]) -> UploadClaims:
        return UploadClaims(
            tenant_id=TenantId(UUID(str(claims["tenant_id"]))),
            storage_key=str(claims["storage_key"]),
            kind=str(claims["kind"]),
            uploaded_by=UserId(UUID(str(claims["uploaded_by"]))),
        )

    async def resolve_download(self, token: str, *, now: datetime) -> DownloadedObject:
        claims = self._tokens.decode(token, purpose="get", now=now)
        data = await self.read(str(claims["storage_key"]))
        content_type = str(claims.get("content_type") or "application/octet-stream")
        return DownloadedObject(data=data, content_type=content_type)

    async def read(self, storage_key: str) -> bytes:
        path = self._path_for(storage_key)
        if not path.is_file():
            raise NotFoundError(f"No object at storage key {storage_key!r}.")
        return await asyncio.to_thread(path.read_bytes)

    async def write(self, storage_key: str, data: bytes) -> None:
        path = self._path_for(storage_key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

    async def delete(self, storage_key: str) -> None:
        path = self._path_for(storage_key)
        await asyncio.to_thread(path.unlink, True)

    def _path_for(self, storage_key: str) -> Path:
        # Reject anything that could escape ``self._root`` via `..` or an
        # absolute path segment - `storage_key` normally comes from
        # `new_storage_key` (safe by construction) but this is the last line
        # of defence against a tampered or hand-crafted one.
        candidate = (self._root / storage_key).resolve()
        if self._root.resolve() not in candidate.parents and candidate != self._root.resolve():
            raise ValidationError("Storage key resolves outside the storage root.")
        return candidate
