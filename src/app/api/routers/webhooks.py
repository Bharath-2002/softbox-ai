"""Inbound webhooks from external providers, plus upload verification (D17)
— ``docs/ARCHITECTURE.md``'s §8 router table designates
``/api/v1/webhooks/*`` for both.

No blanket router-level dependency: each provider (Instagram, payment, ...)
authenticates a callback its own way — a signature header or shared secret
verified against the raw body — not a bearer token. The upload route below
carries its own verification the same way: the presigned token's signature
*is* the authentication, checked inside ``ObjectStorage.accept_upload``, not
by a router-level dependency that would require a session this route
deliberately has none of (bytes here come straight from a browser's PUT,
which the presigned URL never asked to authenticate as a tenant member).
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
    data = await request.body()
    now = clock.now()
    claims = await object_storage.accept_upload(token, data, now=now)

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
