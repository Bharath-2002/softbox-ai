"""Approval queue endpoints (M6) under ``/admin`` — list/filter, approve,
reject with reason, and a per-product bulk approve.

All gated on ``Capability.CATALOG_APPROVE``, not ``PRODUCT_MANAGE`` — a
distinct capability already existed for this (``entities.roles``' dedicated
``APPROVER`` role holds only it), unused until this chunk.

``GET /catalog-images`` lists **live** images only
(``CatalogImageRepository.list_page``'s own definition of "queue" — see
that port's docstring); ``status`` defaults to unset, listing every live
status, since the bulk-approve view needs a product's full current state,
not only ``pending_approval`` rows.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    ApproveCatalogImageDep,
    BulkApproveCatalogImagesForProductDep,
    ListCatalogImagesForReviewDep,
    RejectCatalogImageDep,
)
from app.entities.capabilities import Capability
from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.shared.ids import (
    AssetId,
    CatalogImageId,
    CatalogImageSlotId,
    GenerationItemId,
    ProductId,
    ProductVariantId,
    UserId,
)

router = APIRouter()
_approve = [Depends(require_capability(Capability.CATALOG_APPROVE))]


class CatalogImageResponse(BaseModel):
    id: CatalogImageId
    variant_id: ProductVariantId
    catalog_image_slot_id: CatalogImageSlotId
    asset_id: AssetId
    generation_item_id: GenerationItemId
    status: str
    is_primary: bool
    approved_by: UserId | None
    approved_at: datetime | None
    rejection_reason: str | None
    updated_at: datetime

    @staticmethod
    def from_entity(i: CatalogImage) -> CatalogImageResponse:
        return CatalogImageResponse(
            id=i.id,
            variant_id=i.variant_id,
            catalog_image_slot_id=i.catalog_image_slot_id,
            asset_id=i.asset_id,
            generation_item_id=i.generation_item_id,
            status=i.status.value,
            is_primary=i.is_primary,
            approved_by=i.approved_by,
            approved_at=i.approved_at,
            rejection_reason=i.rejection_reason,
            updated_at=i.updated_at,
        )


class CatalogImagePageResponse(BaseModel):
    items: list[CatalogImageResponse]
    next_cursor: str | None


@router.get("/catalog-images", response_model=CatalogImagePageResponse, dependencies=_approve)
async def list_catalog_images_for_review(
    principal: PrincipalDep,
    use_case: ListCatalogImagesForReviewDep,
    status: CatalogImageStatus | None = None,
    product_id: ProductId | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> CatalogImagePageResponse:
    assert principal.tenant_id is not None
    page = await use_case(
        tenant_id=principal.tenant_id,
        status=status,
        product_id=product_id,
        cursor=cursor,
        limit=limit,
    )
    return CatalogImagePageResponse(
        items=[CatalogImageResponse.from_entity(i) for i in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/catalog-images/{image_id}/approve",
    response_model=CatalogImageResponse,
    dependencies=_approve,
)
async def approve_catalog_image(
    image_id: CatalogImageId, principal: PrincipalDep, use_case: ApproveCatalogImageDep
) -> CatalogImageResponse:
    assert principal.tenant_id is not None
    image = await use_case(
        tenant_id=principal.tenant_id, image_id=image_id, approved_by=principal.user_id
    )
    return CatalogImageResponse.from_entity(image)


class RejectCatalogImageRequest(BaseModel):
    reason: str


@router.post(
    "/catalog-images/{image_id}/reject",
    response_model=CatalogImageResponse,
    dependencies=_approve,
)
async def reject_catalog_image(
    image_id: CatalogImageId,
    body: RejectCatalogImageRequest,
    principal: PrincipalDep,
    use_case: RejectCatalogImageDep,
) -> CatalogImageResponse:
    assert principal.tenant_id is not None
    image = await use_case(
        tenant_id=principal.tenant_id,
        image_id=image_id,
        reason=body.reason,
        rejected_by=principal.user_id,
    )
    return CatalogImageResponse.from_entity(image)


class BulkApproveResponse(BaseModel):
    approved: int


@router.post(
    "/products/{product_id}/catalog-images/approve-all",
    response_model=BulkApproveResponse,
    dependencies=_approve,
)
async def bulk_approve_catalog_images_for_product(
    product_id: ProductId,
    principal: PrincipalDep,
    use_case: BulkApproveCatalogImagesForProductDep,
) -> BulkApproveResponse:
    assert principal.tenant_id is not None
    approved = await use_case(
        tenant_id=principal.tenant_id, product_id=product_id, approved_by=principal.user_id
    )
    return BulkApproveResponse(approved=approved)
