from __future__ import annotations

from app.entities.image_slots import InputImageSlot
from app.shared.ids import CategoryId, InputImageSlotId, TenantId


class InMemoryInputImageSlotRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, InputImageSlotId], InputImageSlot] = {}

    async def get(self, tenant_id: TenantId, slot_id: InputImageSlotId) -> InputImageSlot | None:
        return self._rows.get((tenant_id, slot_id))

    async def add(self, slot: InputImageSlot) -> None:
        self._rows[(slot.tenant_id, slot.id)] = slot

    async def update(self, slot: InputImageSlot) -> None:
        self._rows[(slot.tenant_id, slot.id)] = slot

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[InputImageSlot]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[InputImageSlot]:
        wanted = set(category_ids)
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id in wanted
        ]
        return sorted(matches, key=lambda row: row.position)
