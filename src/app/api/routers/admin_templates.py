"""Template endpoints (D14) under ``/admin`` — chunk of the M3 Admin API.

Two separate creation routes rather than one polymorphic endpoint switching
on a ``kind`` field — the same "two separate write routes" shape D16's
settings router uses (see its module docstring): ``authored``'s only
required field is ``prompt_template``, ``from-upload``'s is
``source_asset_id``, and a single endpoint would need conditional
validation to enforce that instead of the request shape enforcing it.

``POST .../analyse`` runs ``TemplateAnalysisAgent`` synchronously, inline in
the request — there is no task queue yet (that is M5's `TaskQueue` port).
This is a known interim shape, not a final one: once M5's queue exists, this
route should enqueue a step instead of blocking on a provider call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    ArchiveTemplateDep,
    CreateAuthoredTemplateDep,
    CreateTemplateFromUploadDep,
    ListTemplatesDep,
    TemplateAnalysisAgentDep,
)
from app.entities.capabilities import Capability
from app.entities.catalog_template import CatalogTemplate
from app.shared.ids import AssetId, CatalogImageSlotId, CatalogTemplateId

router = APIRouter()
_manage = [Depends(require_capability(Capability.TEMPLATE_MANAGE))]


class TemplateResponse(BaseModel):
    id: CatalogTemplateId
    catalog_image_slot_id: CatalogImageSlotId
    name: str
    version: int
    is_default: bool
    kind: str
    status: str
    source_asset_id: AssetId | None
    prompt_template: str | None
    analysis: dict[str, Any] | None
    analysis_error: str | None
    analysed_at: datetime | None

    @staticmethod
    def from_entity(t: CatalogTemplate) -> TemplateResponse:
        return TemplateResponse(
            id=t.id,
            catalog_image_slot_id=t.catalog_image_slot_id,
            name=t.name,
            version=t.version,
            is_default=t.is_default,
            kind=t.kind.value,
            status=t.status.value,
            source_asset_id=t.source_asset_id,
            prompt_template=t.prompt_template,
            analysis=t.analysis,
            analysis_error=t.analysis_error,
            analysed_at=t.analysed_at,
        )


class CreateAuthoredTemplateRequest(BaseModel):
    name: str
    prompt_template: str


class CreateTemplateFromUploadRequest(BaseModel):
    name: str
    source_asset_id: AssetId


@router.post(
    "/catalog-image-slots/{slot_id}/templates/authored",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_authored_template(
    slot_id: CatalogImageSlotId,
    body: CreateAuthoredTemplateRequest,
    principal: PrincipalDep,
    use_case: CreateAuthoredTemplateDep,
) -> TemplateResponse:
    assert principal.tenant_id is not None
    template = await use_case(
        tenant_id=principal.tenant_id,
        catalog_image_slot_id=slot_id,
        name=body.name,
        prompt_template=body.prompt_template,
        actor_user_id=principal.user_id,
    )
    return TemplateResponse.from_entity(template)


@router.post(
    "/catalog-image-slots/{slot_id}/templates/from-upload",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_template_from_upload(
    slot_id: CatalogImageSlotId,
    body: CreateTemplateFromUploadRequest,
    principal: PrincipalDep,
    use_case: CreateTemplateFromUploadDep,
) -> TemplateResponse:
    assert principal.tenant_id is not None
    template = await use_case(
        tenant_id=principal.tenant_id,
        catalog_image_slot_id=slot_id,
        name=body.name,
        source_asset_id=body.source_asset_id,
        actor_user_id=principal.user_id,
    )
    return TemplateResponse.from_entity(template)


@router.get(
    "/catalog-image-slots/{slot_id}/templates",
    response_model=list[TemplateResponse],
)
async def list_templates(
    slot_id: CatalogImageSlotId, principal: PrincipalDep, use_case: ListTemplatesDep
) -> list[TemplateResponse]:
    assert principal.tenant_id is not None
    templates = await use_case(tenant_id=principal.tenant_id, catalog_image_slot_id=slot_id)
    return [TemplateResponse.from_entity(t) for t in templates]


@router.post(
    "/templates/{template_id}/analyse", response_model=TemplateResponse, dependencies=_manage
)
async def analyse_template(
    template_id: CatalogTemplateId, principal: PrincipalDep, agent: TemplateAnalysisAgentDep
) -> TemplateResponse:
    assert principal.tenant_id is not None
    template = await agent.run(tenant_id=principal.tenant_id, template_id=template_id)
    return TemplateResponse.from_entity(template)


@router.post(
    "/templates/{template_id}/archive", response_model=TemplateResponse, dependencies=_manage
)
async def archive_template(
    template_id: CatalogTemplateId, principal: PrincipalDep, use_case: ArchiveTemplateDep
) -> TemplateResponse:
    assert principal.tenant_id is not None
    template = await use_case(tenant_id=principal.tenant_id, template_id=template_id)
    return TemplateResponse.from_entity(template)
