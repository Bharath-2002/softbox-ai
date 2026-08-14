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
from app.bootstrap.di import InputImageValidationAgentDep, RecomputeProductReadinessDep
from app.entities.capabilities import Capability
from app.entities.product import Product
from app.entities.product_input_image import ProductInputImage
from app.shared.ids import (
    CategoryId,
    CategorySpecVersionId,
    ProductId,
    ProductInputImageId,
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


class InputImageResponse(BaseModel):
    id: ProductInputImageId
    status: str
    rejection_reason: str | None

    @staticmethod
    def from_entity(i: ProductInputImage) -> InputImageResponse:
        return InputImageResponse(
            id=i.id, status=i.status.value, rejection_reason=i.rejection_reason
        )


@router.post(
    "/input-images/{image_id}/validate", response_model=InputImageResponse, dependencies=_manage
)
async def validate_input_image(
    image_id: ProductInputImageId, principal: PrincipalDep, agent: InputImageValidationAgentDep
) -> InputImageResponse:
    assert principal.tenant_id is not None
    image = await agent.run(tenant_id=principal.tenant_id, image_id=image_id)
    return InputImageResponse.from_entity(image)
