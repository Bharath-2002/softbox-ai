"""Bulk action (M6): approve every `pending_approval` catalog image for one
product in a single transaction. One page, not a loop over pages — a
product's live image count is bounded by its (small, admin-configured)
number of catalog image slots per variant, the same "naturally bounded, not
open-ended" reasoning `CatalogImageRepository.list_page`'s own docstring
draws between a product catalog (needs cursor pagination) and a category
tree (does not). But "bounded" is not "small": a product with many axis
variants (colour, size, ...) multiplies slots by variant count, so this
still asks for one row past the limit and refuses to silently approve a
partial set — a truncated bulk-approve that reports success is worse than
one that fails loudly and asks the caller to page.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImageStatus
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import ConflictError, NotFoundError
from app.shared.ids import ProductId, TenantId, UserId

_BULK_LIMIT = 200


class BulkApproveCatalogImagesForProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, product_id: ProductId, approved_by: UserId
    ) -> int:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            product = await uow.products.get(tenant_id, product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            images = await uow.catalog_images.list_page(
                tenant_id,
                status=CatalogImageStatus.PENDING_APPROVAL,
                product_id=product_id,
                after=None,
                limit=_BULK_LIMIT + 1,
            )
            if len(images) > _BULK_LIMIT:
                raise ConflictError(
                    "Too many pending images to approve in one request; approve in smaller batches."
                )
            for image in images:
                image.approve(approved_by=approved_by, now=now)
                await uow.catalog_images.update(image)
                await uow.audit_log.record(
                    tenant_id,
                    actor_user_id=approved_by,
                    action="catalog_image.approved",
                    subject_type="catalog_image",
                    subject_id=image.id,
                    before={"status": "pending_approval"},
                    after={"status": image.status.value},
                    now=now,
                )
            return len(images)
