from __future__ import annotations

from app.entities.attribute_definition import AttributeDefinition
from app.shared.ids import AttributeDefinitionId, CategoryId, TenantId


class InMemoryAttributeDefinitionRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, AttributeDefinitionId], AttributeDefinition] = {}

    async def get(
        self, tenant_id: TenantId, definition_id: AttributeDefinitionId
    ) -> AttributeDefinition | None:
        return self._rows.get((tenant_id, definition_id))

    async def add(self, definition: AttributeDefinition) -> None:
        self._rows[(definition.tenant_id, definition.id)] = definition

    async def update(self, definition: AttributeDefinition) -> None:
        self._rows[(definition.tenant_id, definition.id)] = definition

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[AttributeDefinition]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[AttributeDefinition]:
        wanted = set(category_ids)
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.category_id in wanted
        ]
        return sorted(matches, key=lambda row: row.position)
