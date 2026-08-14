"""Requests a presigned upload (D17) under ``/admin`` — the authenticated
half of the upload flow. The browser then PUTs directly to the returned
URL, which for today's only backend lands on ``webhooks.py``'s unauthenticated
upload route, never back here.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import RequestUploadDep
from app.entities.asset import AssetKind
from app.entities.capabilities import Capability

router = APIRouter()
_manage = [Depends(require_capability(Capability.TEMPLATE_MANAGE))]


class RequestUploadRequest(BaseModel):
    kind: AssetKind
    extension: str
    content_type: str


class PresignedUploadResponse(BaseModel):
    url: str
    method: str
    headers: dict[str, str]
    storage_key: str
    expires_at: datetime


@router.post(
    "/assets/uploads",
    response_model=PresignedUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def request_upload(
    body: RequestUploadRequest, principal: PrincipalDep, use_case: RequestUploadDep
) -> PresignedUploadResponse:
    assert principal.tenant_id is not None
    upload = await use_case(
        tenant_id=principal.tenant_id,
        kind=body.kind,
        extension=body.extension,
        content_type=body.content_type,
        uploaded_by=principal.user_id,
    )
    return PresignedUploadResponse(
        url=upload.url,
        method=upload.method,
        headers=upload.headers,
        storage_key=upload.storage_key,
        expires_at=upload.expires_at,
    )
