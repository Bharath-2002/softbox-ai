"""Operator plane: platform admins only (D4).

Structurally separate from the ``admin`` router rather than a capability
check within it — a platform admin's authority does not come from, and is
not limited by, any tenant's role assignments (``Principal`` docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_platform_admin
from app.bootstrap.di import StartImpersonationDep
from app.shared.ids import TenantId, UserId

router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(require_platform_admin)]
)


class ImpersonateRequest(BaseModel):
    target_user_id: UserId
    target_tenant_id: TenantId
    reason: str


class ImpersonateResponse(BaseModel):
    access_token: str


@router.post("/impersonate", response_model=ImpersonateResponse)
async def impersonate(
    body: ImpersonateRequest, principal: PrincipalDep, use_case: StartImpersonationDep
) -> ImpersonateResponse:
    result = await use_case(
        admin_user_id=principal.user_id,
        target_user_id=body.target_user_id,
        target_tenant_id=body.target_tenant_id,
        reason=body.reason,
    )
    return ImpersonateResponse(access_token=result.access_token)
