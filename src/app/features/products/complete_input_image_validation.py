"""Finishes an input image's validation: re-fetches the row inside its own
transaction (never trusting what ``agents.input_image_validation`` carried
across its Pillow work) and lands on ``ready`` or ``rejected`` depending on
the verdict.
"""

from __future__ import annotations

from app.entities.product_input_image import ProductInputImage
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import ProductInputImageId, TenantId


class CompleteInputImageValidation:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        image_id: ProductInputImageId,
        passed: bool,
        reason: str | None,
    ) -> ProductInputImage:
        async with self._uow_factory(tenant_id) as uow:
            image = await uow.product_input_images.get(tenant_id, image_id)
            if image is None:
                raise NotFoundError("Input image not found.")

            now = self._clock.now()
            before_status = image.status.value
            if passed:
                image.mark_ready(now=now)
            else:
                image.mark_rejected(reason=reason or "Validation failed.", now=now)
            await uow.product_input_images.update(image)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="product_input_image.validation_completed",
                subject_type="product_input_image",
                subject_id=image.id,
                before={"status": before_status},
                after={"status": image.status.value, "rejection_reason": image.rejection_reason},
                now=now,
            )

            return image
