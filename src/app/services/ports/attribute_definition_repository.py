"""Custom-field definition storage (D11). Tenant id is explicit on every
method. ``list_for_categories`` is the bulk form ``spec_inheritance``'s
root->leaf resolver needs — one query across a whole ancestor chain rather
than one round trip per category.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.attribute_definition import AttributeDefinition
from app.shared.ids import AttributeDefinitionId, CategoryId, TenantId


class AttributeDefinitionRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, definition_id: AttributeDefinitionId
    ) -> AttributeDefinition | None: ...

    async def add(self, definition: AttributeDefinition) -> None: ...

    async def update(self, definition: AttributeDefinition) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[AttributeDefinition]:
        """Only definitions this category itself owns, ordered by
        ``position`` — not inherited ones. See ``spec_inheritance`` for the
        resolved, inheritance-aware view."""
        ...

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[AttributeDefinition]:
        """Every definition owned by any of ``category_ids`` — the bulk
        fetch behind resolving a whole ancestor chain in one query."""
        ...
