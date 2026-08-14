"""A tenant's product (D11, D12): one row, `attributes` JSONB holding every
tenant-defined field, with a handful of platform-meaningful ones projected
into real columns (`title`, `sku`, `price_amount`, `price_currency`) by the
write path — see `services.attribute_model_compiler` for how a category's
`AttributeDefinition` rows compile into the Pydantic model that validates
`attributes` before a product is created, and D11's module docs (referenced
from `attribute_definition.py`) for why `semantic_role` is what drives which
fields get promoted.

`spec_version_id` is pinned at creation (D15) and never changes — a later
`category_spec_versions` publish does not move this product's spec out from
under it. Reading "this product's resolved spec" is just
`CategorySpecVersionRepository.get(tenant_id, product.spec_version_id)`; no
new snapshot-building logic is needed, since a `CategorySpecVersion.snapshot`
is already the fully-resolved blob a publish wrote.

Only `create` exists here so far. The full lifecycle (`draft ─▶ ready ─▶
generating ─▶ review ─▶ approved ─▶ publishing ─▶ published`, with
`needs_attention` reachable from several states) spans M4 through M7 —
CLAUDE.md says not to build a transition with nothing to call it yet, so
`ProductStatus` names every state the diagram in `docs/ARCHITECTURE.md` §6
describes (matching what the migration's `CHECK` constraint allows), but
entity methods for `ready`/`needs_attention`/etc. land with the use cases
that actually drive them (readiness needs `product_input_images`, which
doesn't exist yet).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.ids import (
    CategoryId,
    CategorySpecVersionId,
    ProductId,
    TenantId,
    UserId,
    new_product_id,
)


class ProductStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    NEEDS_ATTENTION = "needs_attention"
    GENERATING = "generating"
    REVIEW = "review"
    REJECTED = "rejected"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"


@dataclass
class Product:
    id: ProductId
    tenant_id: TenantId
    category_id: CategoryId
    spec_version_id: CategorySpecVersionId
    attributes: dict[str, Any]
    title: str | None
    sku: str | None
    price_amount: int | None
    price_currency: str | None
    status: ProductStatus
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        category_id: CategoryId,
        spec_version_id: CategorySpecVersionId,
        *,
        attributes: dict[str, Any],
        created_by: UserId,
        now: datetime,
        title: str | None = None,
        sku: str | None = None,
        price_amount: int | None = None,
        price_currency: str | None = None,
    ) -> Product:
        return Product(
            id=new_product_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            spec_version_id=spec_version_id,
            attributes=attributes,
            title=title,
            sku=sku,
            price_amount=price_amount,
            price_currency=price_currency,
            status=ProductStatus.DRAFT,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
