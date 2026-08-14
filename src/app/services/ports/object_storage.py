"""Object storage (D17, D11 upload posture). Bytes never pass through the
business API — a caller asks for a ``PresignedUpload`` and the browser PUTs
directly to ``PresignedUpload.url``, never to a route this codebase's
``admin``/``platform``/``public`` planes serve. ``read``/``write``/``delete``
are for trusted server-side callers only (the upload-verification use case
reading back what a client just PUT, a worker writing a derivative
rendition) — never exposed at a public route.

No ``tenant_id`` on ``read``/``write``/``delete``: unlike a repository, a
storage key already encodes which tenant it belongs to (``new_storage_key``
below), and by the time server-side code is reading/writing bytes the
authorization decision (which tenant may touch this key) has already been
made by whatever called in — the same shape ``EmailSender`` uses for not
taking a tenant.

No real adapter exists yet — no S3/R2 bucket or credentials are configured
(see CHECKLIST.md M3 STATE). ``LocalObjectStorage`` (the only adapter today)
is a genuinely functional local-filesystem implementation for dev/test, the
same role ``ConsoleEmailSender`` plays before SMTP credentials existed —
not a stub, but not what runs in production either.

``accept_upload``/``resolve_download`` exist only because a same-process
backend (today's only adapter) has no separate storage service to presign a
*real* URL against — the "presigned URL" it hands back points at this
process's own ``/api/v1/webhooks/uploads/{token}`` route, which has no
session and no bearer token (the token's signature is the entire
authorization decision). ``UploadClaims`` carries what that unauthenticated
route needs to know — which tenant, what asset kind, who requested it — sealed
inside the signed token by ``presign_put`` so a route with no other
authentication cannot be tricked into writing into the wrong tenant's
namespace. A real S3/R2 adapter would never implement these two methods
meaningfully (uploads never reach this process at all); they stay on this
port rather than a separate one because only one adapter has ever existed
here, and splitting a port for a backend that does not exist yet is the
premature abstraction CLAUDE.md warns against — revisit when a second
adapter actually needs a different shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.shared.ids import TenantId, UserId


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    method: str
    headers: dict[str, str]
    storage_key: str
    expires_at: datetime


@dataclass(frozen=True)
class UploadClaims:
    tenant_id: TenantId
    storage_key: str
    kind: str
    uploaded_by: UserId


class ObjectStorage(Protocol):
    def new_storage_key(self, tenant_id: TenantId, *, kind: str, extension: str) -> str: ...

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
    ) -> PresignedUpload: ...

    async def presign_get(
        self, storage_key: str, *, now: datetime, expires_in: timedelta
    ) -> str: ...

    async def peek_upload(self, token: str, *, now: datetime) -> tuple[UploadClaims, int]:
        """Validates the token and returns its claims plus the size cap it
        declared — without touching any bytes. Lets a route bound how much
        of an unauthenticated request body it will ever read *before*
        reading any of it, rather than learning the cap only after buffering
        the whole thing (what a bare ``accept_upload`` call would do)."""
        ...

    async def accept_upload(self, token: str, data: bytes, *, now: datetime) -> UploadClaims: ...

    async def resolve_download(self, token: str, *, now: datetime) -> bytes: ...

    async def read(self, storage_key: str) -> bytes: ...

    async def write(self, storage_key: str, data: bytes) -> None: ...

    async def delete(self, storage_key: str) -> None: ...
