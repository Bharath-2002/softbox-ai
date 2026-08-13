"""Category taxonomy endpoints (D10, D15) under ``/admin`` — the first M2
entity wired to HTTP. Included into ``admin.router`` so it inherits
``require_tenant_context`` by construction; write endpoints additionally
require a capability (``TAXONOMY_MANAGE`` for structural edits,
``CATALOG_PUBLISH`` for publishing — the same capability D4 already grants
to owner/admin/catalog_manager for exactly this action). Read endpoints
need only the router-level tenant-context gate — a viewer with no
capabilities can still see the catalog structure.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    CreateCategoryDep,
    GetCategoryDep,
    GetPublishedCategorySpecDep,
    ListCategoryChildrenDep,
    MoveCategoryDep,
    PublishCategorySpecDep,
    UpdateCategoryDep,
)
from app.entities.capabilities import Capability
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.shared.ids import CategoryId

router = APIRouter()


class CategoryResponse(BaseModel):
    id: CategoryId
    parent_id: CategoryId | None
    key: str
    name: str
    slug: str
    description: str | None
    position: int
    is_active: bool
    depth: int
    path: str
    current_spec_version: int | None
    draft_spec_version: int | None

    @staticmethod
    def from_entity(category: Category) -> CategoryResponse:
        return CategoryResponse(
            id=category.id,
            parent_id=category.parent_id,
            key=category.key,
            name=category.name,
            slug=category.slug,
            description=category.description,
            position=category.position,
            is_active=category.is_active,
            depth=category.depth,
            path=category.path,
            current_spec_version=category.current_spec_version,
            draft_spec_version=category.draft_spec_version,
        )


class CreateCategoryRequest(BaseModel):
    key: str
    name: str
    slug: str
    parent_id: CategoryId | None = None
    description: str | None = None
    position: int = 0


class UpdateCategoryRequest(BaseModel):
    name: str
    description: str | None = None
    position: int = 0
    is_active: bool = True


class MoveCategoryRequest(BaseModel):
    new_parent_id: CategoryId | None = None


class CategorySpecVersionResponse(BaseModel):
    id: str
    version: int
    status: str
    published_by: str
    published_at: str
    change_summary: dict[str, Any] | None

    @staticmethod
    def from_entity(version: CategorySpecVersion) -> CategorySpecVersionResponse:
        return CategorySpecVersionResponse(
            id=str(version.id),
            version=version.version,
            status=version.status.value,
            published_by=str(version.published_by),
            published_at=version.published_at.isoformat(),
            change_summary=version.change_summary,
        )


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_capability(Capability.TAXONOMY_MANAGE))],
)
async def create_category(
    body: CreateCategoryRequest, principal: PrincipalDep, use_case: CreateCategoryDep
) -> CategoryResponse:
    assert principal.tenant_id is not None  # guaranteed by require_tenant_context
    category = await use_case(
        tenant_id=principal.tenant_id,
        key=body.key,
        name=body.name,
        slug=body.slug,
        parent_id=body.parent_id,
        description=body.description,
        position=body.position,
        actor_user_id=principal.user_id,
    )
    return CategoryResponse.from_entity(category)


@router.get("/categories/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: CategoryId, principal: PrincipalDep, use_case: GetCategoryDep
) -> CategoryResponse:
    assert principal.tenant_id is not None
    category = await use_case(tenant_id=principal.tenant_id, category_id=category_id)
    return CategoryResponse.from_entity(category)


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    principal: PrincipalDep,
    use_case: ListCategoryChildrenDep,
    parent_id: CategoryId | None = None,
) -> list[CategoryResponse]:
    assert principal.tenant_id is not None
    categories = await use_case(tenant_id=principal.tenant_id, parent_id=parent_id)
    return [CategoryResponse.from_entity(c) for c in categories]


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    dependencies=[Depends(require_capability(Capability.TAXONOMY_MANAGE))],
)
async def update_category(
    category_id: CategoryId,
    body: UpdateCategoryRequest,
    principal: PrincipalDep,
    use_case: UpdateCategoryDep,
) -> CategoryResponse:
    assert principal.tenant_id is not None
    category = await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        name=body.name,
        description=body.description,
        position=body.position,
        is_active=body.is_active,
        actor_user_id=principal.user_id,
    )
    return CategoryResponse.from_entity(category)


@router.post(
    "/categories/{category_id}/move",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_capability(Capability.TAXONOMY_MANAGE))],
)
async def move_category(
    category_id: CategoryId,
    body: MoveCategoryRequest,
    principal: PrincipalDep,
    use_case: MoveCategoryDep,
) -> None:
    assert principal.tenant_id is not None
    await use_case(
        tenant_id=principal.tenant_id,
        category_id=category_id,
        new_parent_id=body.new_parent_id,
        actor_user_id=principal.user_id,
    )


@router.post(
    "/categories/{category_id}/publish",
    response_model=CategorySpecVersionResponse,
    dependencies=[Depends(require_capability(Capability.CATALOG_PUBLISH))],
)
async def publish_category_spec(
    category_id: CategoryId, principal: PrincipalDep, use_case: PublishCategorySpecDep
) -> CategorySpecVersionResponse:
    assert principal.tenant_id is not None
    version = await use_case(
        tenant_id=principal.tenant_id, category_id=category_id, actor_user_id=principal.user_id
    )
    return CategorySpecVersionResponse.from_entity(version)


@router.get("/categories/{category_id}/spec-versions/{version}")
async def get_published_category_spec(
    category_id: CategoryId,
    version: int,
    principal: PrincipalDep,
    use_case: GetPublishedCategorySpecDep,
) -> dict[str, Any]:
    assert principal.tenant_id is not None
    return await use_case(tenant_id=principal.tenant_id, category_id=category_id, version=version)
