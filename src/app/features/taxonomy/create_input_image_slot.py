"""Creates an input image slot (D13) — a category-level capture pool entry."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.entities.image_slots import InputImageSlot
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateInputImageSlot:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        key: str,
        label: str,
        description: str | None = None,
        capture_guidance: str | None = None,
        example_asset_id: UUID | None = None,
        normalisation: dict[str, Any] | None = None,
        is_required: bool = True,
        position: int = 0,
        actor_user_id: UserId,
    ) -> InputImageSlot:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            slot = InputImageSlot.create(
                tenant_id,
                category_id,
                key=key,
                label=label,
                now=now,
                description=description,
                capture_guidance=capture_guidance,
                example_asset_id=example_asset_id,
                normalisation=normalisation,
                is_required=is_required,
                position=position,
            )
            await uow.input_image_slots.add(slot)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="input_image_slot.created",
                subject_type="input_image_slot",
                subject_id=slot.id,
                before=None,
                after={"key": key, "category_id": str(category_id)},
                now=now,
            )

            return slot
