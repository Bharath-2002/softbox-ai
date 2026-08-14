"""Edits a catalog image slot's non-referential fields. ``key`` is not
editable (D15's rename-forbidden case). ``aspect_ratio``/``target_width``/
``target_height`` ARE editable — they describe the rendered output, not a
referential identity, so changing them does not need retire-and-add.
"""

from __future__ import annotations

from app.entities.image_slots import CatalogImageSlot
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageSlotId, TenantId, UserId


class UpdateCatalogImageSlot:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        slot_id: CatalogImageSlotId,
        label: str,
        description: str | None,
        aspect_ratio: str,
        target_width: int,
        target_height: int,
        is_required: bool,
        position: int,
        actor_user_id: UserId,
    ) -> CatalogImageSlot:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            slot = await uow.catalog_image_slots.get(tenant_id, slot_id)
            if slot is None:
                raise NotFoundError("Catalog image slot not found.")

            before = {"label": slot.label, "aspect_ratio": slot.aspect_ratio}

            slot.label = label
            slot.description = description
            slot.aspect_ratio = aspect_ratio
            slot.target_width = target_width
            slot.target_height = target_height
            slot.is_required = is_required
            slot.position = position
            slot.updated_at = now
            await uow.catalog_image_slots.update(slot)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_image_slot.updated",
                subject_type="catalog_image_slot",
                subject_id=slot_id,
                before=before,
                after={"label": label, "aspect_ratio": aspect_ratio},
                now=now,
            )

            return slot
