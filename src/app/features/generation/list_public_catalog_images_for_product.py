"""A product's storefront-visible imagery (D18, M8): live, ``APPROVED``
catalog images for one product, joined through ``product_variants`` by
``CatalogImageRepository.list_page`` — the same query the approval queue's
"all images for a product" view already uses, filtered to the one status a
shopper may see.

No pagination surfaced, matching ``ListPublicCategoryChildren``'s and
``ListCategoryChildren``'s reasoning: a product's image count is bounded by
its catalog image slots times its variants, both admin-configured, not an
open-ended collection a shopper could grow without limit.

Gated on the product itself being published, not just live images
existing — otherwise a shopper who already knows or guesses a draft
product's id could enumerate its pre-launch photos before the product page
itself is reachable. Same ``NotFoundError`` either way, matching
``GetPublicProduct``.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.product import ProductStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.errors import NotFoundError
from app.shared.ids import ProductId, TenantId

_MAX_IMAGES = 200


class ListPublicCatalogImagesForProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, tenant_id: TenantId, product_id: ProductId) -> list[CatalogImage]:
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None or product.status is not ProductStatus.PUBLISHED:
                raise NotFoundError("Product not found.")

            return await uow.catalog_images.list_page(
                tenant_id,
                status=CatalogImageStatus.APPROVED,
                product_id=product_id,
                after=None,
                limit=_MAX_IMAGES,
            )
