from __future__ import annotations

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.shared.ids import CatalogImageSlotId, InputImageSlotId, TenantId

_Key = tuple[TenantId, CatalogImageSlotId, InputImageSlotId]


class InMemoryCatalogSlotInputRequirementRepository:
    def __init__(self) -> None:
        self._rows: dict[_Key, CatalogSlotInputRequirement] = {}

    def _key(self, requirement: CatalogSlotInputRequirement) -> _Key:
        return (
            requirement.tenant_id,
            requirement.catalog_image_slot_id,
            requirement.input_image_slot_id,
        )

    async def get(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> CatalogSlotInputRequirement | None:
        return self._rows.get((tenant_id, catalog_image_slot_id, input_image_slot_id))

    async def add(self, requirement: CatalogSlotInputRequirement) -> None:
        self._rows[self._key(requirement)] = requirement

    async def update(self, requirement: CatalogSlotInputRequirement) -> None:
        self._rows[self._key(requirement)] = requirement

    async def remove(
        self,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        input_image_slot_id: InputImageSlotId,
    ) -> None:
        self._rows.pop((tenant_id, catalog_image_slot_id, input_image_slot_id), None)

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        matches = [
            row
            for (tid, cid, _), row in self._rows.items()
            if tid == tenant_id and cid == catalog_image_slot_id
        ]
        return sorted(matches, key=lambda row: row.prompt_position)

    async def list_for_input_slot(
        self, tenant_id: TenantId, input_image_slot_id: InputImageSlotId
    ) -> list[CatalogSlotInputRequirement]:
        return [
            row
            for (tid, _, iid), row in self._rows.items()
            if tid == tenant_id and iid == input_image_slot_id
        ]
