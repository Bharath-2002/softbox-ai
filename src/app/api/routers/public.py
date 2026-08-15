"""Unauthenticated storefront plane.

No router-level auth dependency — a shopper is not a signed-in principal.
Every route instead depends on ``PublicTenantIdDep``, which resolves the
tenant from the request's Host header (CLAUDE.md §9, D4) against
``tenant_domains`` (M8 chunk 1) — the storefront's equivalent of
``PrincipalDep``/``require_tenant_context``, minus any notion of a signed-in
user.

Categories are the first route: no pricing or PII sensitivity, and its read
model (``ListPublicCategoryChildren``) already existed as a variant of the
admin one, so this route proves the resolver end to end without also
needing a new read model built at the same time. Products and published
catalog images follow in the next chunk, reusing the same
``PublicTenantIdDep``.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps.tenant_resolution import PublicTenantIdDep
from app.bootstrap.di import ListPublicCategoryChildrenDep
from app.entities.category import Category
from app.shared.ids import CategoryId

router = APIRouter(prefix="/public", tags=["public"])


class PublicCategoryResponse(BaseModel):
    """Deliberately slimmer than admin's ``CategoryResponse`` — no
    ``key``, ``current_spec_version``/``draft_spec_version``: those are
    catalog-management internals a shopper has no use for and should
    never see."""

    id: CategoryId
    parent_id: CategoryId | None
    name: str
    slug: str
    description: str | None
    position: int

    @staticmethod
    def from_entity(category: Category) -> PublicCategoryResponse:
        return PublicCategoryResponse(
            id=category.id,
            parent_id=category.parent_id,
            name=category.name,
            slug=category.slug,
            description=category.description,
            position=category.position,
        )


@router.get("/categories", response_model=list[PublicCategoryResponse])
async def list_categories(
    tenant_id: PublicTenantIdDep,
    use_case: ListPublicCategoryChildrenDep,
    parent_id: CategoryId | None = None,
) -> list[PublicCategoryResponse]:
    categories = await use_case(tenant_id=tenant_id, parent_id=parent_id)
    return [PublicCategoryResponse.from_entity(category) for category in categories]
