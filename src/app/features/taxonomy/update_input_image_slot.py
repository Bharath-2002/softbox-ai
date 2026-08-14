"""Edits an input image slot's non-referential fields. ``key`` is not
editable (D15's rename-forbidden case)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.entities.image_slots import InputImageSlot
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import InputImageSlotId, TenantId, UserId


class UpdateInputImageSlot:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        slot_id: InputImageSlotId,
        label: str,
        description: str | None,
        capture_guidance: str | None,
        example_asset_id: UUID | None,
        normalisation: dict[str, Any],
        is_required: bool,
        position: int,
        actor_user_id: UserId,
    ) -> InputImageSlot:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            slot = await uow.input_image_slots.get(tenant_id, slot_id)
            if slot is None:
                raise NotFoundError("Input image slot not found.")

            before = {"label": slot.label, "is_required": slot.is_required}

            slot.label = label
            slot.description = description
            slot.capture_guidance = capture_guidance
            slot.example_asset_id = example_asset_id
            slot.normalisation = normalisation
            slot.is_required = is_required
            slot.position = position
            slot.updated_at = now
            await uow.input_image_slots.update(slot)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="input_image_slot.updated",
                subject_type="input_image_slot",
                subject_id=slot_id,
                before=before,
                after={"label": label, "is_required": is_required},
                now=now,
            )

            return slot
