"""Creates a variant against its parent product's *pinned* spec snapshot
(D12, D15) — the same "read `spec_version_id`'s snapshot, never LIVE tables"
rule `product_readiness` and `CreateProduct` both follow, applied here to
`variant_axes` instead of `attribute_definitions`. A variant is always a
child of an already-created product, so there is no separate "resolve the
category's current spec" step: the product's own pin already answers that.

``attributes`` (the sparse override) is stored as given, unvalidated — it is
deliberately a partial dict (D12), and the compiled Pydantic model from
`attribute_model_compiler` requires every `is_required` field to be present,
which a sparse override will almost always violate by design. Validating a
*partial* attribute dict against the full model is a different function
nobody has needed yet; storage-layer-only for now, same deferral
`product_variants`' own CHECKLIST entry already states for the merged view.
"""

from __future__ import annotations

from typing import Any

from app.entities.product_variant import ProductVariant
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.variant_axis_validation import validate_axis_values
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import ProductId, TenantId, UserId


class CreateProductVariant:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        product_id: ProductId,
        axis_values: dict[str, str],
        created_by: UserId,
        sku: str | None = None,
        attributes: dict[str, Any] | None = None,
        is_default: bool = False,
        position: int = 0,
    ) -> ProductVariant:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError(
                    "The product's pinned spec version is missing (data inconsistency)."
                )

            problems = validate_axis_values(spec_version.snapshot, axis_values)
            if problems:
                raise ValidationError("; ".join(problems))

            now = self._clock.now()
            variant = ProductVariant.create(
                tenant_id,
                product_id,
                axis_values=axis_values,
                created_by=created_by,
                now=now,
                sku=sku,
                attributes=attributes,
                is_default=is_default,
                position=position,
            )
            await uow.product_variants.add(variant)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=created_by,
                action="product_variant.created",
                subject_type="product_variant",
                subject_id=variant.id,
                before=None,
                after={"product_id": str(product_id), "axis_values": axis_values},
                now=now,
            )

            return variant
