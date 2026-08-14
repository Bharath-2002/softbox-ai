"""Product endpoints (D11, D12) under ``/admin`` — the first M4 routes.

``POST .../recompute-readiness`` is the only way ``ready``/``needs_attention``
change today. Nothing calls it automatically yet — no attribute-editing or
input-image-capture use case exists to trigger a recompute from, so an admin
(or, once built, those use cases themselves) calls this explicitly. Same
shape as `seed-stock-presets`: a real, callable use case with no automatic
trigger, the trigger explicitly flagged rather than invented.

``POST .../input-images/{id}/validate`` runs `InputImageValidationAgent`
synchronously, inline in the request — the same known-interim shape
``POST .../templates/{id}/analyse`` already uses, for the same reason:
there is no task queue yet (M5's `TaskQueue` port).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import (
    CaptureProductInputImageDep,
    CreateGenerationRequestDep,
    CreateProductDep,
    CreateProductVariantDep,
    FanOutGenerationItemsDep,
    InputImageValidationAgentDep,
    ListProductsDep,
    RecomputeProductReadinessDep,
)
from app.entities.capabilities import Capability
from app.entities.generation_request import GenerationRequest
from app.entities.product import Product
from app.entities.product_input_image import ProductInputImage
from app.entities.product_variant import ProductVariant
from app.shared.ids import (
    AssetId,
    CategoryId,
    CategorySpecVersionId,
    GenerationItemId,
    GenerationRequestId,
    InputImageSlotId,
    ProductId,
    ProductInputImageId,
    ProductVariantId,
)

router = APIRouter()
_manage = [Depends(require_capability(Capability.PRODUCT_MANAGE))]


class ProductResponse(BaseModel):
    id: ProductId
    category_id: CategoryId
    spec_version_id: CategorySpecVersionId
    attributes: dict[str, Any]
    title: str | None
    sku: str | None
    price_amount: int | None
    price_currency: str | None
    status: str
    updated_at: datetime

    @staticmethod
    def from_entity(p: Product) -> ProductResponse:
        return ProductResponse(
            id=p.id,
            category_id=p.category_id,
            spec_version_id=p.spec_version_id,
            attributes=p.attributes,
            title=p.title,
            sku=p.sku,
            price_amount=p.price_amount,
            price_currency=p.price_currency,
            status=p.status.value,
            updated_at=p.updated_at,
        )


class CreateProductRequest(BaseModel):
    category_id: CategoryId
    attributes: dict[str, Any]


@router.post("/products", response_model=ProductResponse, status_code=201, dependencies=_manage)
async def create_product(
    body: CreateProductRequest, principal: PrincipalDep, use_case: CreateProductDep
) -> ProductResponse:
    assert principal.tenant_id is not None
    product = await use_case(
        tenant_id=principal.tenant_id,
        category_id=body.category_id,
        attributes=body.attributes,
        created_by=principal.user_id,
    )
    return ProductResponse.from_entity(product)


class ProductPageResponse(BaseModel):
    items: list[ProductResponse]
    next_cursor: str | None


@router.get("/products", response_model=ProductPageResponse, dependencies=_manage)
async def list_products(
    principal: PrincipalDep,
    use_case: ListProductsDep,
    category_id: CategoryId | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> ProductPageResponse:
    assert principal.tenant_id is not None
    page = await use_case(
        tenant_id=principal.tenant_id, category_id=category_id, cursor=cursor, limit=limit
    )
    return ProductPageResponse(
        items=[ProductResponse.from_entity(p) for p in page.items], next_cursor=page.next_cursor
    )


@router.post(
    "/products/{product_id}/recompute-readiness",
    response_model=ProductResponse,
    dependencies=_manage,
)
async def recompute_product_readiness(
    product_id: ProductId, principal: PrincipalDep, use_case: RecomputeProductReadinessDep
) -> ProductResponse:
    assert principal.tenant_id is not None
    product = await use_case(tenant_id=principal.tenant_id, product_id=product_id)
    return ProductResponse.from_entity(product)


class ProductVariantResponse(BaseModel):
    id: ProductVariantId
    product_id: ProductId
    sku: str | None
    axis_values: dict[str, str]
    attributes: dict[str, Any]
    status: str
    is_default: bool

    @staticmethod
    def from_entity(v: ProductVariant) -> ProductVariantResponse:
        return ProductVariantResponse(
            id=v.id,
            product_id=v.product_id,
            sku=v.sku,
            axis_values=v.axis_values,
            attributes=v.attributes,
            status=v.status.value,
            is_default=v.is_default,
        )


class CreateProductVariantRequest(BaseModel):
    axis_values: dict[str, str]
    sku: str | None = None
    attributes: dict[str, Any] = {}
    is_default: bool = False
    position: int = 0


@router.post(
    "/products/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=_manage,
)
async def create_product_variant(
    product_id: ProductId,
    body: CreateProductVariantRequest,
    principal: PrincipalDep,
    use_case: CreateProductVariantDep,
) -> ProductVariantResponse:
    assert principal.tenant_id is not None
    variant = await use_case(
        tenant_id=principal.tenant_id,
        product_id=product_id,
        axis_values=body.axis_values,
        created_by=principal.user_id,
        sku=body.sku,
        attributes=body.attributes,
        is_default=body.is_default,
        position=body.position,
    )
    return ProductVariantResponse.from_entity(variant)


class InputImageResponse(BaseModel):
    id: ProductInputImageId
    product_id: ProductId
    variant_id: ProductVariantId | None
    input_image_slot_id: InputImageSlotId
    asset_id: AssetId
    status: str
    rejection_reason: str | None

    @staticmethod
    def from_entity(i: ProductInputImage) -> InputImageResponse:
        return InputImageResponse(
            id=i.id,
            product_id=i.product_id,
            variant_id=i.variant_id,
            input_image_slot_id=i.input_image_slot_id,
            asset_id=i.asset_id,
            status=i.status.value,
            rejection_reason=i.rejection_reason,
        )


class CaptureProductInputImageRequest(BaseModel):
    input_image_slot_id: InputImageSlotId
    asset_id: AssetId
    variant_id: ProductVariantId | None = None


@router.post(
    "/products/{product_id}/input-images",
    response_model=InputImageResponse,
    status_code=201,
    dependencies=_manage,
)
async def capture_product_input_image(
    product_id: ProductId,
    body: CaptureProductInputImageRequest,
    principal: PrincipalDep,
    use_case: CaptureProductInputImageDep,
) -> InputImageResponse:
    assert principal.tenant_id is not None
    image = await use_case(
        tenant_id=principal.tenant_id,
        product_id=product_id,
        input_image_slot_id=body.input_image_slot_id,
        asset_id=body.asset_id,
        created_by=principal.user_id,
        variant_id=body.variant_id,
    )
    return InputImageResponse.from_entity(image)


@router.post(
    "/input-images/{image_id}/validate", response_model=InputImageResponse, dependencies=_manage
)
async def validate_input_image(
    image_id: ProductInputImageId, principal: PrincipalDep, agent: InputImageValidationAgentDep
) -> InputImageResponse:
    assert principal.tenant_id is not None
    image = await agent.run(tenant_id=principal.tenant_id, image_id=image_id)
    return InputImageResponse.from_entity(image)


class GenerationRequestResponse(BaseModel):
    id: GenerationRequestId
    product_id: ProductId
    variant_id: ProductVariantId
    status: str
    created_at: datetime

    @staticmethod
    def from_entity(r: GenerationRequest) -> GenerationRequestResponse:
        return GenerationRequestResponse(
            id=r.id,
            product_id=r.product_id,
            variant_id=r.variant_id,
            status=r.status.value,
            created_at=r.created_at,
        )


class CreateGenerationRequestRequest(BaseModel):
    variant_id: ProductVariantId


@router.post(
    "/products/{product_id}/generation-requests",
    response_model=GenerationRequestResponse,
    status_code=201,
    dependencies=_manage,
)
async def create_generation_request(
    product_id: ProductId,
    body: CreateGenerationRequestRequest,
    principal: PrincipalDep,
    use_case: CreateGenerationRequestDep,
) -> GenerationRequestResponse:
    assert principal.tenant_id is not None
    request = await use_case(
        tenant_id=principal.tenant_id,
        product_id=product_id,
        variant_id=body.variant_id,
        requested_by=principal.user_id,
    )
    return GenerationRequestResponse.from_entity(request)


class FanOutResponse(BaseModel):
    item_ids: list[GenerationItemId]


@router.post(
    "/generation-requests/{generation_request_id}/fan-out",
    response_model=FanOutResponse,
    dependencies=_manage,
)
async def fan_out_generation_items(
    generation_request_id: GenerationRequestId,
    principal: PrincipalDep,
    use_case: FanOutGenerationItemsDep,
) -> FanOutResponse:
    assert principal.tenant_id is not None
    items = await use_case(
        tenant_id=principal.tenant_id, generation_request_id=generation_request_id
    )
    return FanOutResponse(item_ids=[item.id for item in items])
