"""Deletes one sharing-join row. Idempotent — removing an already-absent
pairing is not an error, matching ``CatalogSlotInputRequirementRepository.remove``'s
contract.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId, UserId


class DetachInputFromCatalogSlot:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
        actor_user_id: UserId,
    ) -> None:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            await uow.catalog_slot_input_requirements.remove(
                tenant_id, catalog_image_slot_id, input_image_slot_id
            )

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_slot_input_requirement.removed",
                subject_type="catalog_slot_input_requirement",
                subject_id=catalog_image_slot_id,
                before={"input_image_slot_id": str(input_image_slot_id)},
                after=None,
                now=now,
            )
