"""Human-driven approval (M6) — `pending_approval -> approved`, the
counterpart to `complete_catalog_image_qc`'s auto-approve branch. Always
passes a real `approved_by`, unlike that branch's `None` for the
setting-driven path.
"""

from __future__ import annotations

from app.entities.catalog_image import CatalogImage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageId, TenantId, UserId


class ApproveCatalogImage:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, image_id: CatalogImageId, approved_by: UserId
    ) -> CatalogImage:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            image = await uow.catalog_images.get(tenant_id, image_id)
            if image is None:
                raise NotFoundError("Catalog image not found.")

            before_status = image.status.value
            image.approve(approved_by=approved_by, now=now)
            await uow.catalog_images.update(image)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=approved_by,
                action="catalog_image.approved",
                subject_type="catalog_image",
                subject_id=image_id,
                before={"status": before_status},
                after={"status": image.status.value},
                now=now,
            )

            return image
