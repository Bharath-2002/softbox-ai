"""Variant axis storage (D12). Tenant id is explicit on every method. Same
shape as ``AttributeDefinitionRepository`` — ``list_for_categories`` is the
bulk fetch ``spec_inheritance``'s root->leaf resolver needs.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.variant_axis import VariantAxis
from app.shared.ids import CategoryId, TenantId, VariantAxisId


class VariantAxisRepository(Protocol):
    async def get(self, tenant_id: TenantId, axis_id: VariantAxisId) -> VariantAxis | None: ...

    async def add(self, axis: VariantAxis) -> None: ...

    async def update(self, axis: VariantAxis) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[VariantAxis]:
        """Only axes this category itself owns, ordered by ``position`` —
        not inherited ones."""
        ...

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[VariantAxis]:
        """Every axis owned by any of ``category_ids`` — the bulk fetch
        behind resolving a whole ancestor chain in one query."""
        ...
