"""Input image slot storage (D13) — the category-level capture pool. Same
shape as ``AttributeDefinitionRepository``.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.image_slots import InputImageSlot
from app.shared.ids import CategoryId, InputImageSlotId, TenantId


class InputImageSlotRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, slot_id: InputImageSlotId
    ) -> InputImageSlot | None: ...

    async def add(self, slot: InputImageSlot) -> None: ...

    async def update(self, slot: InputImageSlot) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[InputImageSlot]: ...

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[InputImageSlot]: ...
