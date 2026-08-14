"""Inbound webhooks from external providers, plus upload verification (D17)
— ``docs/ARCHITECTURE.md``'s §8 router table designates
``/api/v1/webhooks/*`` for both.

No blanket router-level dependency: each provider (Instagram, payment, ...)
authenticates a callback its own way — a signature header or shared secret
verified against the raw body — not a bearer token. The upload route below
carries its own verification the same way: the presigned token's signature
*is* the authentication, checked inside ``ObjectStorage.peek_upload``, not
by a router-level dependency that would require a session this route
deliberately has none of (bytes here come straight from a browser's PUT,
which the presigned URL never asked to authenticate as a tenant member).

The upload route decodes the token — learning the size cap it declared —
**before** reading any of the request body, then bounds the streamed read
to that cap. An unauthenticated caller controls this body, so buffering it
first and only checking the size afterward (what a single ``await
request.body()`` would do) would let a forged or oversized request make
this process buffer an unbounded amount of memory before anything rejects
it.

The download route below carries no comparable size concern — it reads
bytes this process already wrote, not an attacker-controlled request body
— so ``ObjectStorage.resolve_download`` decodes the token and reads in one
call, unlike the upload route's decode-then-bounded-stream split.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps.object_storage import ObjectStorageDep
from app.bootstrap.di import ClockDep, VerifyAndRegisterUploadDep
from app.entities.asset import AssetKind
from app.shared.errors import ValidationError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.put("/uploads/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def receive_upload(
    token: str,
    request: Request,
    object_storage: ObjectStorageDep,
    verify_and_register_upload: VerifyAndRegisterUploadDep,
    clock: ClockDep,
) -> Response:
    now = clock.now()
    claims, max_bytes = await object_storage.peek_upload(token, now=now)

    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            over_cap = int(declared_length) > max_bytes
        except ValueError:
            over_cap = False  # malformed header - the streamed read below still bounds it
        if over_cap:
            raise ValidationError("Upload exceeds the size declared when it was requested.")

    buffer = bytearray()
    async for chunk in request.stream():
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise ValidationError("Upload exceeds the size declared when it was requested.")

    await object_storage.accept_upload(token, bytes(buffer), now=now)

    try:
        kind = AssetKind(claims.kind)
    except ValueError as exc:
        raise ValidationError(f"Unknown asset kind {claims.kind!r} in upload token.") from exc

    await verify_and_register_upload(
        tenant_id=claims.tenant_id,
        storage_key=claims.storage_key,
        kind=kind,
        uploaded_by=claims.uploaded_by,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/uploads/{token}")
async def download_asset(token: str, object_storage: ObjectStorageDep, clock: ClockDep) -> Response:
    downloaded = await object_storage.resolve_download(token, now=clock.now())
    return Response(content=downloaded.data, media_type=downloaded.content_type)
