"""Input/catalog image slot pool and sharing-join endpoints (D13) under
``/admin`` — chunk C of the M2 Admin API, same shape as
``admin_taxonomy.py``/``admin_attributes.py``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    AttachInputToCatalogSlotDep,
    CreateCatalogImageSlotDep,
    CreateInputImageSlotDep,
    DetachInputFromCatalogSlotDep,
    ListCatalogImageSlotsDep,
    ListCatalogSlotInputRequirementsDep,
    ListInputImageSlotsDep,
    UpdateCatalogImageSlotDep,
    UpdateCatalogSlotInputRequirementDep,
    UpdateInputImageSlotDep,
)
from app.entities.capabilities import Capability
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.shared.ids import CatalogImageSlotId, CategoryId, InputImageSlotId

router = APIRouter()
_manage = [Depends(require_capability(Capability.TAXONOMY_MANAGE))]


class InputImageSlotResponse(BaseModel):
    id: InputImageSlotId
    category_id: CategoryId
    key: str
    label: str
    description: str | None
    capture_guidance: str | None
    example_asset_id: UUID | None
    is_required: bool
    position: int

    @staticmethod
    def from_entity(s: InputImageSlot) -> InputImageSlotResponse:
        return InputImageSlotResponse(
            id=s.id,
            category_id=s.category_id,
            key=s.key,
            label=s.label,
            description=s.description,
            capture_guidance=s.capture_guidance,
            example_asset_id=s.example_asset_id,
            is_required=s.is_required,
            position=s.position,
        )


class CreateInputImageSlotRequest(BaseModel):
    key: str
    label: str
    description: str | None = None
    capture_guidance: str | None = None
    is_required: bool = True
    position: int = 0


class UpdateInputImageSlotRequest(BaseModel):
    label: str
    description: str | None = None
    capture_guidance: str | None = None
    example_asset_id: UUID | None = None
    normalisation: dict[str, object] = {}
    is_required: bool = True
    position: int = 0


@router.post(
    "/categories/{category_id}/input-image-slots",
    response_model=InputImageSlotResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_input_image_slot(
    category_id: CategoryId,
    body: CreateInputImageSlotRequest,
    principal: PrincipalDep,
    use_case: CreateInputImageSlotDep,
) -> InputImageSlotResponse:
    assert principal.tenant_id is not None
    slot = await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        key=body.key,
        label=body.label,
        description=body.description,
        capture_guidance=body.capture_guidance,
        is_required=body.is_required,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return InputImageSlotResponse.from_entity(slot)


@router.get(
    "/categories/{category_id}/input-image-slots",
    response_model=list[InputImageSlotResponse],
)
async def list_input_image_slots(
    category_id: CategoryId, principal: PrincipalDep, use_case: ListInputImageSlotsDep
) -> list[InputImageSlotResponse]:
    assert principal.tenant_id is not None
    slots = await use_case(tenant_id=principal.tenant_id, category_id=category_id)
    return [InputImageSlotResponse.from_entity(s) for s in slots]


@router.patch(
    "/input-image-slots/{slot_id}", response_model=InputImageSlotResponse, dependencies=_manage
)
async def update_input_image_slot(
    slot_id: InputImageSlotId,
    body: UpdateInputImageSlotRequest,
    principal: PrincipalDep,
    use_case: UpdateInputImageSlotDep,
) -> InputImageSlotResponse:
    assert principal.tenant_id is not None
    slot = await use_case(
        tenant_id=principal.tenant_id,
        slot_id=slot_id,
        label=body.label,
        description=body.description,
        capture_guidance=body.capture_guidance,
        example_asset_id=body.example_asset_id,
        normalisation=body.normalisation,
        is_required=body.is_required,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return InputImageSlotResponse.from_entity(slot)


class CatalogImageSlotResponse(BaseModel):
    id: CatalogImageSlotId
    category_id: CategoryId
    key: str
    label: str
    description: str | None
    aspect_ratio: str
    target_width: int
    target_height: int
    is_required: bool
    position: int

    @staticmethod
    def from_entity(s: CatalogImageSlot) -> CatalogImageSlotResponse:
        return CatalogImageSlotResponse(
            id=s.id,
            category_id=s.category_id,
            key=s.key,
            label=s.label,
            description=s.description,
            aspect_ratio=s.aspect_ratio,
            target_width=s.target_width,
            target_height=s.target_height,
            is_required=s.is_required,
            position=s.position,
        )


class CreateCatalogImageSlotRequest(BaseModel):
    key: str
    label: str
    aspect_ratio: str
    target_width: int
    target_height: int
    description: str | None = None
    is_required: bool = True
    position: int = 0


class UpdateCatalogImageSlotRequest(BaseModel):
    label: str
    aspect_ratio: str
    target_width: int
    target_height: int
    description: str | None = None
    is_required: bool = True
    position: int = 0


@router.post(
    "/categories/{category_id}/catalog-image-slots",
    response_model=CatalogImageSlotResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_catalog_image_slot(
    category_id: CategoryId,
    body: CreateCatalogImageSlotRequest,
    principal: PrincipalDep,
    use_case: CreateCatalogImageSlotDep,
) -> CatalogImageSlotResponse:
    assert principal.tenant_id is not None
    slot = await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        key=body.key,
        label=body.label,
        aspect_ratio=body.aspect_ratio,
        target_width=body.target_width,
        target_height=body.target_height,
        description=body.description,
        is_required=body.is_required,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return CatalogImageSlotResponse.from_entity(slot)


@router.get(
    "/categories/{category_id}/catalog-image-slots",
    response_model=list[CatalogImageSlotResponse],
)
async def list_catalog_image_slots(
    category_id: CategoryId, principal: PrincipalDep, use_case: ListCatalogImageSlotsDep
) -> list[CatalogImageSlotResponse]:
    assert principal.tenant_id is not None
    slots = await use_case(tenant_id=principal.tenant_id, category_id=category_id)
    return [CatalogImageSlotResponse.from_entity(s) for s in slots]


@router.patch(
    "/catalog-image-slots/{slot_id}",
    response_model=CatalogImageSlotResponse,
    dependencies=_manage,
)
async def update_catalog_image_slot(
    slot_id: CatalogImageSlotId,
    body: UpdateCatalogImageSlotRequest,
    principal: PrincipalDep,
    use_case: UpdateCatalogImageSlotDep,
) -> CatalogImageSlotResponse:
    assert principal.tenant_id is not None
    slot = await use_case(
        tenant_id=principal.tenant_id,
        slot_id=slot_id,
        label=body.label,
        description=body.description,
        aspect_ratio=body.aspect_ratio,
        target_width=body.target_width,
        target_height=body.target_height,
        is_required=body.is_required,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return CatalogImageSlotResponse.from_entity(slot)


class RequirementResponse(BaseModel):
    catalog_image_slot_id: CatalogImageSlotId
    input_image_slot_id: InputImageSlotId
    role: str
    prompt_position: int
    is_required: bool

    @staticmethod
    def from_entity(r: CatalogSlotInputRequirement) -> RequirementResponse:
        return RequirementResponse(
            catalog_image_slot_id=r.catalog_image_slot_id,
            input_image_slot_id=r.input_image_slot_id,
            role=r.role,
            prompt_position=r.prompt_position,
            is_required=r.is_required,
        )


class AttachRequirementRequest(BaseModel):
    input_image_slot_id: InputImageSlotId
    role: str
    prompt_position: int
    is_required: bool = True


class UpdateRequirementRequest(BaseModel):
    role: str
    prompt_position: int
    is_required: bool = True


@router.post(
    "/catalog-image-slots/{catalog_image_slot_id}/requirements",
    response_model=RequirementResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def attach_input_to_catalog_slot(
    catalog_image_slot_id: CatalogImageSlotId,
    body: AttachRequirementRequest,
    principal: PrincipalDep,
    use_case: AttachInputToCatalogSlotDep,
) -> RequirementResponse:
    assert principal.tenant_id is not None
    requirement = await use_case(
        tenant_id=principal.tenant_id,
        catalog_image_slot_id=catalog_image_slot_id,
        input_image_slot_id=body.input_image_slot_id,
        role=body.role,
        prompt_position=body.prompt_position,
        is_required=body.is_required,
        actor_user_id=principal.user_id,
    )
    return RequirementResponse.from_entity(requirement)


@router.get(
    "/catalog-image-slots/{catalog_image_slot_id}/requirements",
    response_model=list[RequirementResponse],
)
async def list_catalog_slot_requirements(
    catalog_image_slot_id: CatalogImageSlotId,
    principal: PrincipalDep,
    use_case: ListCatalogSlotInputRequirementsDep,
) -> list[RequirementResponse]:
    assert principal.tenant_id is not None
    requirements = await use_case(
        tenant_id=principal.tenant_id, catalog_image_slot_id=catalog_image_slot_id
    )
    return [RequirementResponse.from_entity(r) for r in requirements]


@router.patch(
    "/catalog-image-slots/{catalog_image_slot_id}/requirements/{input_image_slot_id}",
    response_model=RequirementResponse,
    dependencies=_manage,
)
async def update_catalog_slot_requirement(
    catalog_image_slot_id: CatalogImageSlotId,
    input_image_slot_id: InputImageSlotId,
    body: UpdateRequirementRequest,
    principal: PrincipalDep,
    use_case: UpdateCatalogSlotInputRequirementDep,
) -> RequirementResponse:
    assert principal.tenant_id is not None
    requirement = await use_case(
        tenant_id=principal.tenant_id,
        catalog_image_slot_id=catalog_image_slot_id,
        input_image_slot_id=input_image_slot_id,
        role=body.role,
        prompt_position=body.prompt_position,
        is_required=body.is_required,
        actor_user_id=principal.user_id,
    )
    return RequirementResponse.from_entity(requirement)


@router.delete(
    "/catalog-image-slots/{catalog_image_slot_id}/requirements/{input_image_slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=_manage,
)
async def detach_input_from_catalog_slot(
    catalog_image_slot_id: CatalogImageSlotId,
    input_image_slot_id: InputImageSlotId,
    principal: PrincipalDep,
    use_case: DetachInputFromCatalogSlotDep,
) -> None:
    assert principal.tenant_id is not None
    await use_case(
        tenant_id=principal.tenant_id,
        catalog_image_slot_id=catalog_image_slot_id,
        input_image_slot_id=input_image_slot_id,
        actor_user_id=principal.user_id,
    )
