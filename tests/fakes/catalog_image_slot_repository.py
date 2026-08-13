from __future__ import annotations

from app.entities.image_slots import CatalogImageSlot
from app.shared.ids import CatalogImageSlotId, CategoryId, TenantId


class InMemoryCatalogImageSlotRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, CatalogImageSlotId], CatalogImageSlot] = {}

    async def get(
        self, tenant_id: TenantId, slot_id: CatalogImageSlotId
    ) -> CatalogImageSlot | None:
        return self._rows.get((tenant_id, slot_id))

    async def add(self, slot: CatalogImageSlot) -> None:
        self._rows[(slot.tenant_id, slot.id)] = slot

    async def update(self, slot: CatalogImageSlot) -> None:
        self._rows[(slot.tenant_id, slot.id)] = slot

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CatalogImageSlot]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[CatalogImageSlot]:
        wanted = set(category_ids)
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id in wanted
        ]
        return sorted(matches, key=lambda row: row.position)
