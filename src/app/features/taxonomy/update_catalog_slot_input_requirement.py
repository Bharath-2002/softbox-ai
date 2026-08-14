"""Edits a sharing-join row's ``role``/``prompt_position``/``is_required``.
The pair itself (``catalog_image_slot_id``, ``input_image_slot_id``) is the
natural key and is not editable — detach and reattach instead.
"""

from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId, UserId


class UpdateCatalogSlotInputRequirement:
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
        is_required: bool,
        actor_user_id: UserId,
    ) -> CatalogSlotInputRequirement:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            requirement = await uow.catalog_slot_input_requirements.get(
                tenant_id, catalog_image_slot_id, input_image_slot_id
            )
            if requirement is None:
                raise NotFoundError("Catalog slot input requirement not found.")

            before = {"role": requirement.role, "prompt_position": requirement.prompt_position}

            requirement.role = role
            requirement.prompt_position = prompt_position
            requirement.is_required = is_required
            await uow.catalog_slot_input_requirements.update(requirement)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_slot_input_requirement.updated",
                subject_type="catalog_slot_input_requirement",
                subject_id=catalog_image_slot_id,
                before=before,
                after={"role": role, "prompt_position": prompt_position},
                now=now,
            )

            return requirement
