"""Lists a catalog slot's input requirements, ordered by ``prompt_position``
(``CatalogSlotInputRequirementRepository.list_for_catalog_slot``'s
contract)."""

from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CatalogImageSlotId, TenantId


class ListCatalogSlotInputRequirements:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.catalog_slot_input_requirements.list_for_catalog_slot(
                tenant_id, catalog_image_slot_id
            )
