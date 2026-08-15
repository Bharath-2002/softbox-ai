"""Unauthenticated storefront plane.

No router-level auth dependency — a shopper is not a signed-in principal.
Every route instead depends on ``PublicTenantIdDep``, which resolves the
tenant from the request's Host header (CLAUDE.md §9, D4) against
``tenant_domains`` (M8 chunk 1) — the storefront's equivalent of
``PrincipalDep``/``require_tenant_context``, minus any notion of a signed-in
user.

Categories were the first route: no pricing or PII sensitivity, and its read
model (``ListPublicCategoryChildren``) already existed as a variant of the
admin one, so it proved the resolver end to end without also needing a new
read model at the same time. Products follow the same shape:
``ProductStatus.PUBLISHED`` is this catalog's "visible to a shopper" state,
filtered at the repository query (``list_published_page``) rather than
after fetching, so cursor pagination's own page-boundary accounting stays
correct for the rows it excludes.

Catalog images reuse ``RequestDownload`` (M3, CLAUDE.md §11 "private assets
served by signed short-lived URLs") rather than a public CDN URL — there is
no real CDN adapter yet (checklist-flagged, credential-blocked), and a
presigned URL is the only image-delivery mechanism that already exists and
is already correct for a private object store. One presign call per image
in the response, the same "known interim shape, not a hidden N+1" posture
``admin_products.py``'s inline synchronous agent calls already have.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps.tenant_resolution import PublicTenantIdDep
from app.bootstrap.di import (
    GetPublicProductDep,
    ListPublicCatalogImagesForProductDep,
    ListPublicCategoryChildrenDep,
    ListPublicProductsDep,
    RequestDownloadDep,
)
from app.entities.category import Category
from app.entities.product import Product
from app.shared.ids import CatalogImageId, CatalogImageSlotId, CategoryId, ProductId

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


class PublicProductResponse(BaseModel):
    """No ``spec_version_id`` (internal FK) and no ``sku`` (warehouse-facing,
    not shopper-facing) — everything else admin's ``ProductResponse``
    exposes is exactly what a storefront product page needs.

    ``attributes`` is exposed wholesale, though: a category spec (D9/D10)
    can declare fields with no shopper-facing meaning (internal cost,
    supplier notes), and nothing here filters by a field's own visibility.
    No spec field is marked internal-vs-public yet, so there is nothing to
    filter *on* — a known widening, not an oversight, until a spec-level
    visibility flag exists to filter by."""

    id: ProductId
    category_id: CategoryId
    attributes: dict[str, Any]
    title: str | None
    price_amount: int | None
    price_currency: str | None

    @staticmethod
    def from_entity(product: Product) -> PublicProductResponse:
        return PublicProductResponse(
            id=product.id,
            category_id=product.category_id,
            attributes=product.attributes,
            title=product.title,
            price_amount=product.price_amount,
            price_currency=product.price_currency,
        )


class PublicProductPageResponse(BaseModel):
    items: list[PublicProductResponse]
    next_cursor: str | None


@router.get("/products", response_model=PublicProductPageResponse)
async def list_products(
    tenant_id: PublicTenantIdDep,
    use_case: ListPublicProductsDep,
    category_id: CategoryId | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> PublicProductPageResponse:
    page = await use_case(tenant_id=tenant_id, category_id=category_id, cursor=cursor, limit=limit)
    return PublicProductPageResponse(
        items=[PublicProductResponse.from_entity(p) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/products/{product_id}", response_model=PublicProductResponse)
async def get_product(
    product_id: ProductId, tenant_id: PublicTenantIdDep, use_case: GetPublicProductDep
) -> PublicProductResponse:
    product = await use_case(tenant_id=tenant_id, product_id=product_id)
    return PublicProductResponse.from_entity(product)


class PublicCatalogImageResponse(BaseModel):
    id: CatalogImageId
    catalog_image_slot_id: CatalogImageSlotId
    is_primary: bool
    download_url: str


@router.get("/products/{product_id}/images", response_model=list[PublicCatalogImageResponse])
async def list_product_images(
    product_id: ProductId,
    tenant_id: PublicTenantIdDep,
    use_case: ListPublicCatalogImagesForProductDep,
    request_download: RequestDownloadDep,
) -> list[PublicCatalogImageResponse]:
    images = await use_case(tenant_id=tenant_id, product_id=product_id)
    return [
        PublicCatalogImageResponse(
            id=image.id,
            catalog_image_slot_id=image.catalog_image_slot_id,
            is_primary=image.is_primary,
            download_url=await request_download(tenant_id=tenant_id, asset_id=image.asset_id),
        )
        for image in images
    ]
