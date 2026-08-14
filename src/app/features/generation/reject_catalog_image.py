"""Human-driven rejection (M6) — `pending_approval -> rejected`. Nothing in
this codebase auto-rejects, unlike `approve()`'s setting-driven path in
`complete_catalog_image_qc` — a rejection always has a human reason and a
human actor.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageId, TenantId, UserId


class RejectCatalogImage:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        image_id: CatalogImageId,
        reason: str,
        rejected_by: UserId,
    ) -> CatalogImage:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            image = await uow.catalog_images.get(tenant_id, image_id)
            if image is None:
                raise NotFoundError("Catalog image not found.")

            before_status = image.status.value
            image.reject(reason=reason, now=now)
            await uow.catalog_images.update(image)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=rejected_by,
                action="catalog_image.rejected",
                subject_type="catalog_image",
                subject_id=image_id,
                before={"status": before_status},
                after={"status": image.status.value, "rejection_reason": reason},
                now=now,
            )

            return image
