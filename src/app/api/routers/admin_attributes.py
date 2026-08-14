"""Attribute definition and variant axis (+ values) endpoints (D11, D12)
under ``/admin`` — chunk B of the M2 Admin API, same shape as
``admin_taxonomy.py``'s categories: ``TAXONOMY_MANAGE`` gates every write,
reads need only the router-level tenant-context gate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    CreateAttributeDefinitionDep,
    CreateVariantAxisDep,
    CreateVariantAxisValueDep,
    ListAttributeDefinitionsDep,
    ListVariantAxesDep,
    ListVariantAxisValuesDep,
    UpdateAttributeDefinitionDep,
    UpdateVariantAxisDep,
    UpdateVariantAxisValueDep,
)
from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.entities.capabilities import Capability
from app.entities.variant_axis import VariantAxis, VariantAxisValue
from app.shared.ids import (
    AttributeDefinitionId,
    CategoryId,
    VariantAxisId,
    VariantAxisValueId,
)

router = APIRouter()
_manage = [Depends(require_capability(Capability.TAXONOMY_MANAGE))]


class AttributeDefinitionResponse(BaseModel):
    id: AttributeDefinitionId
    category_id: CategoryId
    key: str
    label: str
    help_text: str | None
    data_type: str
    semantic_role: str | None
    is_required: bool
    is_filterable: bool
    is_public: bool
    position: int
    validation: dict[str, Any]
    ui: dict[str, Any]
    default_value: Any | None
    introduced_in_version: int | None
    retired_in_version: int | None

    @staticmethod
    def from_entity(d: AttributeDefinition) -> AttributeDefinitionResponse:
        return AttributeDefinitionResponse(
            id=d.id,
            category_id=d.category_id,
            key=d.key,
            label=d.label,
            help_text=d.help_text,
            data_type=d.data_type.value,
            semantic_role=d.semantic_role.value if d.semantic_role else None,
            is_required=d.is_required,
            is_filterable=d.is_filterable,
            is_public=d.is_public,
            position=d.position,
            validation=d.validation,
            ui=d.ui,
            default_value=d.default_value,
            introduced_in_version=d.introduced_in_version,
            retired_in_version=d.retired_in_version,
        )


class CreateAttributeDefinitionRequest(BaseModel):
    key: str
    label: str
    data_type: AttributeDataType
    help_text: str | None = None
    semantic_role: SemanticRole | None = None
    is_required: bool = False
    is_filterable: bool = False
    is_public: bool = True
    position: int = 0
    validation: dict[str, Any] | None = None
    ui: dict[str, Any] | None = None
    default_value: Any | None = None


class UpdateAttributeDefinitionRequest(BaseModel):
    label: str
    help_text: str | None = None
    semantic_role: SemanticRole | None = None
    is_required: bool = False
    is_filterable: bool = False
    is_public: bool = True
    position: int = 0
    validation: dict[str, Any] = {}
    ui: dict[str, Any] = {}
    default_value: Any | None = None


@router.post(
    "/categories/{category_id}/attribute-definitions",
    response_model=AttributeDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_attribute_definition(
    category_id: CategoryId,
    body: CreateAttributeDefinitionRequest,
    principal: PrincipalDep,
    use_case: CreateAttributeDefinitionDep,
) -> AttributeDefinitionResponse:
    assert principal.tenant_id is not None
    definition = await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        key=body.key,
        label=body.label,
        data_type=body.data_type,
        help_text=body.help_text,
        semantic_role=body.semantic_role,
        is_required=body.is_required,
        is_filterable=body.is_filterable,
        is_public=body.is_public,
        position=body.position,
        validation=body.validation,
        ui=body.ui,
        default_value=body.default_value,
        actor_user_id=principal.user_id,
    )
    return AttributeDefinitionResponse.from_entity(definition)


@router.get(
    "/categories/{category_id}/attribute-definitions",
    response_model=list[AttributeDefinitionResponse],
)
async def list_attribute_definitions(
    category_id: CategoryId, principal: PrincipalDep, use_case: ListAttributeDefinitionsDep
) -> list[AttributeDefinitionResponse]:
    assert principal.tenant_id is not None
    definitions = await use_case(tenant_id=principal.tenant_id, category_id=category_id)
    return [AttributeDefinitionResponse.from_entity(d) for d in definitions]


@router.patch(
    "/attribute-definitions/{definition_id}",
    response_model=AttributeDefinitionResponse,
    dependencies=_manage,
)
async def update_attribute_definition(
    definition_id: AttributeDefinitionId,
    body: UpdateAttributeDefinitionRequest,
    principal: PrincipalDep,
    use_case: UpdateAttributeDefinitionDep,
) -> AttributeDefinitionResponse:
    assert principal.tenant_id is not None
    definition = await use_case(
        tenant_id=principal.tenant_id,
        definition_id=definition_id,
        label=body.label,
        help_text=body.help_text,
        semantic_role=body.semantic_role,
        is_required=body.is_required,
        is_filterable=body.is_filterable,
        is_public=body.is_public,
        position=body.position,
        validation=body.validation,
        ui=body.ui,
        default_value=body.default_value,
        actor_user_id=principal.user_id,
    )
    return AttributeDefinitionResponse.from_entity(definition)


class VariantAxisResponse(BaseModel):
    id: VariantAxisId
    category_id: CategoryId
    key: str
    label: str
    position: int
    affects_imagery: bool
    introduced_in_version: int | None
    retired_in_version: int | None

    @staticmethod
    def from_entity(a: VariantAxis) -> VariantAxisResponse:
        return VariantAxisResponse(
            id=a.id,
            category_id=a.category_id,
            key=a.key,
            label=a.label,
            position=a.position,
            affects_imagery=a.affects_imagery,
            introduced_in_version=a.introduced_in_version,
            retired_in_version=a.retired_in_version,
        )


class CreateVariantAxisRequest(BaseModel):
    key: str
    label: str
    affects_imagery: bool
    position: int = 0


class UpdateVariantAxisRequest(BaseModel):
    label: str
    affects_imagery: bool
    position: int = 0


@router.post(
    "/categories/{category_id}/variant-axes",
    response_model=VariantAxisResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_variant_axis(
    category_id: CategoryId,
    body: CreateVariantAxisRequest,
    principal: PrincipalDep,
    use_case: CreateVariantAxisDep,
) -> VariantAxisResponse:
    assert principal.tenant_id is not None
    axis = await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        key=body.key,
        label=body.label,
        affects_imagery=body.affects_imagery,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return VariantAxisResponse.from_entity(axis)


@router.get("/categories/{category_id}/variant-axes", response_model=list[VariantAxisResponse])
async def list_variant_axes(
    category_id: CategoryId, principal: PrincipalDep, use_case: ListVariantAxesDep
) -> list[VariantAxisResponse]:
    assert principal.tenant_id is not None
    axes = await use_case(tenant_id=principal.tenant_id, category_id=category_id)
    return [VariantAxisResponse.from_entity(a) for a in axes]


@router.patch("/variant-axes/{axis_id}", response_model=VariantAxisResponse, dependencies=_manage)
async def update_variant_axis(
    axis_id: VariantAxisId,
    body: UpdateVariantAxisRequest,
    principal: PrincipalDep,
    use_case: UpdateVariantAxisDep,
) -> VariantAxisResponse:
    assert principal.tenant_id is not None
    axis = await use_case(
        tenant_id=principal.tenant_id,
        axis_id=axis_id,
        label=body.label,
        affects_imagery=body.affects_imagery,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return VariantAxisResponse.from_entity(axis)


class VariantAxisValueResponse(BaseModel):
    id: VariantAxisValueId
    axis_id: VariantAxisId
    value: str
    label: str
    metadata: dict[str, Any]

    @staticmethod
    def from_entity(v: VariantAxisValue) -> VariantAxisValueResponse:
        return VariantAxisValueResponse(
            id=v.id, axis_id=v.axis_id, value=v.value, label=v.label, metadata=v.metadata
        )


class CreateVariantAxisValueRequest(BaseModel):
    value: str
    label: str
    metadata: dict[str, Any] | None = None


class UpdateVariantAxisValueRequest(BaseModel):
    label: str
    metadata: dict[str, Any] = {}


@router.post(
    "/variant-axes/{axis_id}/values",
    response_model=VariantAxisValueResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=_manage,
)
async def create_variant_axis_value(
    axis_id: VariantAxisId,
    body: CreateVariantAxisValueRequest,
    principal: PrincipalDep,
    use_case: CreateVariantAxisValueDep,
) -> VariantAxisValueResponse:
    assert principal.tenant_id is not None
    value = await use_case(
        tenant_id=principal.tenant_id,
        axis_id=axis_id,
        value=body.value,
        label=body.label,
        metadata=body.metadata,
        actor_user_id=principal.user_id,
    )
    return VariantAxisValueResponse.from_entity(value)


@router.get("/variant-axes/{axis_id}/values", response_model=list[VariantAxisValueResponse])
async def list_variant_axis_values(
    axis_id: VariantAxisId, principal: PrincipalDep, use_case: ListVariantAxisValuesDep
) -> list[VariantAxisValueResponse]:
    assert principal.tenant_id is not None
    values = await use_case(tenant_id=principal.tenant_id, axis_id=axis_id)
    return [VariantAxisValueResponse.from_entity(v) for v in values]


@router.patch(
    "/variant-axis-values/{value_id}",
    response_model=VariantAxisValueResponse,
    dependencies=_manage,
)
async def update_variant_axis_value(
    value_id: VariantAxisValueId,
    body: UpdateVariantAxisValueRequest,
    principal: PrincipalDep,
    use_case: UpdateVariantAxisValueDep,
) -> VariantAxisValueResponse:
    assert principal.tenant_id is not None
    value = await use_case(
        tenant_id=principal.tenant_id,
        value_id=value_id,
        label=body.label,
        metadata=body.metadata,
        actor_user_id=principal.user_id,
    )
    return VariantAxisValueResponse.from_entity(value)
