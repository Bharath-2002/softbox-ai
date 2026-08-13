from __future__ import annotations

from app.entities.category import Category
from app.shared.ids import CategoryId, TenantId


class InMemoryCategoryRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, CategoryId], Category] = {}

    async def get(self, tenant_id: TenantId, category_id: CategoryId) -> Category | None:
        return self._rows.get((tenant_id, category_id))

    async def add(self, category: Category) -> None:
        self._rows[(category.tenant_id, category.id)] = category

    async def update(self, category: Category) -> None:
        self._rows[(category.tenant_id, category.id)] = category

    async def list_children(
        self, tenant_id: TenantId, parent_id: CategoryId | None
    ) -> list[Category]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.parent_id == parent_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def list_subtree(self, tenant_id: TenantId, category_id: CategoryId) -> list[Category]:
        root = self._rows.get((tenant_id, category_id))
        if root is None:
            return []
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and (row.id == category_id or row.path.startswith(f"{root.path}."))
        ]
        return sorted(matches, key=lambda row: row.path)
