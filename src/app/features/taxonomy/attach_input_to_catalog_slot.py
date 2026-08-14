"""Creates one row of the sharing join (D13): "catalog slot C needs input
slot I, playing role R, at prompt position P." Both sides must belong to
the caller's own tenant — the composite FKs enforce this at the DB level
too, but checking here gives a 404 instead of an opaque constraint error.
"""

from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId, UserId


class AttachInputToCatalogSlot:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
        role: str,
        prompt_position: int,
        is_required: bool = True,
        actor_user_id: UserId,
    ) -> CatalogSlotInputRequirement:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            catalog_slot = await uow.catalog_image_slots.get(tenant_id, catalog_image_slot_id)
            if catalog_slot is None:
                raise NotFoundError("Catalog image slot not found.")
            input_slot = await uow.input_image_slots.get(tenant_id, input_image_slot_id)
            if input_slot is None:
                raise NotFoundError("Input image slot not found.")

            requirement = CatalogSlotInputRequirement.create(
                tenant_id,
                catalog_image_slot_id,
                input_image_slot_id,
                role=role,
                prompt_position=prompt_position,
                now=now,
                is_required=is_required,
            )
            await uow.catalog_slot_input_requirements.add(requirement)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_slot_input_requirement.created",
                subject_type="catalog_slot_input_requirement",
                subject_id=catalog_image_slot_id,
                before=None,
                after={"input_image_slot_id": str(input_image_slot_id), "role": role},
                now=now,
            )

            return requirement
