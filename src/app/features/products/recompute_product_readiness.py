"""Recomputes a product's `ready`/`needs_attention` status against its
pinned spec version (D15, M4 Gate) — the only place `Product.mark_ready`/
`mark_needs_attention` are called from. Nothing triggers this automatically
yet; no attribute-editing or input-image-capture use case exists to call it
from. Product-level only — variant-level readiness reuses the same
`compute_product_readiness` function but is not wired here, deferred to
whichever use case first needs it.
"""

from __future__ import annotations

from app.entities.product import Product, ProductStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.product_readiness import compute_product_readiness
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import ProductId, TenantId


class RecomputeProductReadiness:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId, product_id: ProductId) -> Product:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            spec_version = await uow.category_spec_versions.get(tenant_id, product.spec_version_id)
            if spec_version is None:
                raise NotFoundError("Product's pinned spec version not found.")

            images = await uow.product_input_images.list_for_product(tenant_id, product_id)
            result = compute_product_readiness(
                spec_version.snapshot, attributes=product.attributes, images=images
            )

            now = self._clock.now()
            if result.is_ready:
                product.mark_ready(now=now)
            elif product.status in (ProductStatus.READY, ProductStatus.NEEDS_ATTENTION):
                product.mark_needs_attention(now=now)
            await uow.products.update(product)

            return product
