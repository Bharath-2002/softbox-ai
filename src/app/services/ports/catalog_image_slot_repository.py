"""Catalog image slot storage (D13) — what the category produces. Same
shape as ``AttributeDefinitionRepository``.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.image_slots import CatalogImageSlot
from app.shared.ids import CatalogImageSlotId, CategoryId, TenantId


class CatalogImageSlotRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, slot_id: CatalogImageSlotId
    ) -> CatalogImageSlot | None: ...

    async def add(self, slot: CatalogImageSlot) -> None: ...

    async def update(self, slot: CatalogImageSlot) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CatalogImageSlot]: ...

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[CatalogImageSlot]: ...
