"""Settings endpoints (D16) under ``/admin``.

Deliberately two separate write routes — tenant-level and category-level —
rather than one endpoint accepting a caller-supplied ``scope_type``. A
tenant-bound admin session must never be able to write a platform-wide
default: if ``scope_type`` were a request field, a bug or a deliberately
crafted body could pass ``"platform"`` straight through to ``UpsertSetting``,
which would bind ``tenant_id=None`` and (via the migration's RLS
``WITH CHECK``) actually be *rejected* by the database — but "the DB saves
us" is not a design, it's a coincidence to not rely on. Making ``platform``
unreachable at the route's own shape is cheaper and does not depend on the
RLS policy staying exactly as strict as it is today.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import ResolveSettingDep, UpsertSettingDep
from app.entities.capabilities import Capability
from app.entities.setting import Setting, SettingScope
from app.shared.ids import CategoryId

router = APIRouter()
_manage = [Depends(require_capability(Capability.SETTINGS_MANAGE))]


class SettingResponse(BaseModel):
    key: str
    value: Any

    @staticmethod
    def from_entity(setting: Setting) -> SettingResponse:
        return SettingResponse(key=setting.key, value=setting.value)


class UpsertSettingRequest(BaseModel):
    value: Any


@router.put("/settings/tenant/{key}", response_model=SettingResponse, dependencies=_manage)
async def upsert_tenant_setting(
    key: str, body: UpsertSettingRequest, principal: PrincipalDep, use_case: UpsertSettingDep
) -> SettingResponse:
    assert principal.tenant_id is not None
    setting = await use_case(
        tenant_id=principal.tenant_id,
        scope_type=SettingScope.TENANT,
        scope_id=None,
        key=key,
        value=body.value,
    )
    return SettingResponse.from_entity(setting)


@router.put(
    "/settings/category/{category_id}/{key}",
    response_model=SettingResponse,
    dependencies=_manage,
)
async def upsert_category_setting(
    category_id: CategoryId,
    key: str,
    body: UpsertSettingRequest,
    principal: PrincipalDep,
    use_case: UpsertSettingDep,
) -> SettingResponse:
    assert principal.tenant_id is not None
    setting = await use_case(
        tenant_id=principal.tenant_id,
        scope_type=SettingScope.CATEGORY,
        scope_id=category_id,
        key=key,
        value=body.value,
    )
    return SettingResponse.from_entity(setting)


class ResolvedSettingResponse(BaseModel):
    key: str
    value: Any | None


@router.get("/settings/{key}", response_model=ResolvedSettingResponse)
async def resolve_setting(
    key: str,
    principal: PrincipalDep,
    use_case: ResolveSettingDep,
    category_id: CategoryId | None = None,
) -> ResolvedSettingResponse:
    assert principal.tenant_id is not None
    value = await use_case(tenant_id=principal.tenant_id, key=key, category_id=category_id)
    return ResolvedSettingResponse(key=key, value=value)
