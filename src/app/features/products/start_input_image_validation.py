"""Transitions an input image ``captured -> validating`` (§6.1) and hands
back everything ``agents.input_image_validation`` needs for the Pillow work
it does *outside* this transaction: where the bytes live, and the
already-verified dimensions from ``VerifyAndRegisterUpload``'s upload-time
inspection (``services.image_inspection``) — re-decoding just for width/
height would repeat work the asset row already paid for.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import ProductInputImageId, TenantId


@dataclass(frozen=True)
class InputImageValidationContext:
    image_id: ProductInputImageId
    storage_key: str
    width: int
    height: int


class StartInputImageValidation:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, image_id: ProductInputImageId
    ) -> InputImageValidationContext:
        async with self._uow_factory(tenant_id) as uow:
            image = await uow.product_input_images.get(tenant_id, image_id)
            if image is None:
                raise NotFoundError("Input image not found.")

            asset = await uow.assets.get(tenant_id, image.asset_id)
            if asset is None:
                raise NotFoundError("Source asset not found.")

            image.start_validating(now=self._clock.now())
            await uow.product_input_images.update(image)

            return InputImageValidationContext(
                image_id=image.id,
                storage_key=asset.storage_key,
                width=asset.width,
                height=asset.height,
            )
