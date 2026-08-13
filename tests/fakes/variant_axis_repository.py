from __future__ import annotations

from app.entities.variant_axis import VariantAxis
from app.shared.ids import CategoryId, TenantId, VariantAxisId


class InMemoryVariantAxisRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, VariantAxisId], VariantAxis] = {}

    async def get(self, tenant_id: TenantId, axis_id: VariantAxisId) -> VariantAxis | None:
        return self._rows.get((tenant_id, axis_id))

    async def add(self, axis: VariantAxis) -> None:
        self._rows[(axis.tenant_id, axis.id)] = axis

    async def update(self, axis: VariantAxis) -> None:
        self._rows[(axis.tenant_id, axis.id)] = axis

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[VariantAxis]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[VariantAxis]:
        wanted = set(category_ids)
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id in wanted
        ]
        return sorted(matches, key=lambda row: row.position)
