"""Creates a catalog image slot (D13) — what the category produces."""

from __future__ import annotations

from app.entities.image_slots import CatalogImageSlot
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateCatalogImageSlot:
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
        aspect_ratio: str,
        target_width: int,
        target_height: int,
        description: str | None = None,
        is_required: bool = True,
        position: int = 0,
        actor_user_id: UserId,
    ) -> CatalogImageSlot:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            slot = CatalogImageSlot.create(
                tenant_id,
                category_id,
                key=key,
                label=label,
                aspect_ratio=aspect_ratio,
                target_width=target_width,
                target_height=target_height,
                now=now,
                description=description,
                is_required=is_required,
                position=position,
            )
            await uow.catalog_image_slots.add(slot)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_image_slot.created",
                subject_type="catalog_image_slot",
                subject_id=slot.id,
                before=None,
                after={"key": key, "category_id": str(category_id)},
                now=now,
            )

            return slot
