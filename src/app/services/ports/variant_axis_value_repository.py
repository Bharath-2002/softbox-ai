"""Variant axis value storage (D12) — the enumerated option set for one
axis (e.g. "maroon", "tissue"). Tenant id is explicit on every method.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.variant_axis import VariantAxisValue
from app.shared.ids import TenantId, VariantAxisId, VariantAxisValueId


class VariantAxisValueRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, value_id: VariantAxisValueId
    ) -> VariantAxisValue | None: ...

    async def add(self, value: VariantAxisValue) -> None: ...

    async def update(self, value: VariantAxisValue) -> None: ...

    async def list_for_axis(
        self, tenant_id: TenantId, axis_id: VariantAxisId
    ) -> list[VariantAxisValue]: ...
