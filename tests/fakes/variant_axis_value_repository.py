from __future__ import annotations

from app.entities.variant_axis import VariantAxisValue
from app.shared.ids import TenantId, VariantAxisId, VariantAxisValueId


class InMemoryVariantAxisValueRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, VariantAxisValueId], VariantAxisValue] = {}

    async def get(
        self, tenant_id: TenantId, value_id: VariantAxisValueId
    ) -> VariantAxisValue | None:
        return self._rows.get((tenant_id, value_id))

    async def add(self, value: VariantAxisValue) -> None:
        self._rows[(value.tenant_id, value.id)] = value

    async def update(self, value: VariantAxisValue) -> None:
        self._rows[(value.tenant_id, value.id)] = value

    async def list_for_axis(
        self, tenant_id: TenantId, axis_id: VariantAxisId
    ) -> list[VariantAxisValue]:
        return [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.axis_id == axis_id
        ]
