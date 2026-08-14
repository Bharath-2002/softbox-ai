"""A product's variant (D12): one row per distinct combination of axis
values a tenant sells — colour, fabric, whatever axes the category defines.
`axis_values` is a flat `{axis_key: value}` map (``{"colour": "maroon"}``),
not a normalised join table, the same "JSONB is the source of truth"
storage choice D11 makes for `Product.attributes`.

`attributes` here is a **sparse override** of the parent product's
attributes (D12) — a variant only carries the keys it overrides, never a
full copy. Resolving "this variant's effective attributes" is a merge of
`product.attributes` and `variant.attributes` (variant wins), a service-layer
concern once a use case actually needs the merged view — not this entity's
job, the same division `Product` draws around promoted columns.

Shares `ProductStatus` with `Product` rather than a separate
`VariantStatus` — `docs/ARCHITECTURE.md` §6 titles the diagram "Product /
variant lifecycle" as one shared state machine, not two parallel ones.

Only `create` exists here so far, for the same reason `Product` only has
`create`: the lifecycle transitions land with the use cases that drive them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.entities.product import ProductStatus
from app.shared.ids import ProductId, ProductVariantId, TenantId, UserId, new_product_variant_id


@dataclass
class ProductVariant:
    id: ProductVariantId
    tenant_id: TenantId
    product_id: ProductId
    sku: str | None
    axis_values: dict[str, str]
    attributes: dict[str, Any]
    status: ProductStatus
    is_default: bool
    position: int
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        product_id: ProductId,
        *,
        axis_values: dict[str, str],
        created_by: UserId,
        now: datetime,
        sku: str | None = None,
        attributes: dict[str, Any] | None = None,
        is_default: bool = False,
        position: int = 0,
    ) -> ProductVariant:
        return ProductVariant(
            id=new_product_variant_id(),
            tenant_id=tenant_id,
            product_id=product_id,
            sku=sku,
            axis_values=axis_values,
            attributes=attributes or {},
            status=ProductStatus.DRAFT,
            is_default=is_default,
            position=position,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
