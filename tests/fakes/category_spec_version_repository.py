from __future__ import annotations

from app.entities.category_spec_version import CategorySpecVersion
from app.shared.ids import CategoryId, CategorySpecVersionId, TenantId

_Key = tuple[TenantId, CategorySpecVersionId]


class InMemoryCategorySpecVersionRepository:
    def __init__(self) -> None:
        self._rows: dict[_Key, CategorySpecVersion] = {}

    async def get(
        self, tenant_id: TenantId, version_id: CategorySpecVersionId
    ) -> CategorySpecVersion | None:
        return self._rows.get((tenant_id, version_id))

    async def get_by_version(
        self, tenant_id: TenantId, category_id: CategoryId, version: int
    ) -> CategorySpecVersion | None:
        for row in self._rows.values():
            if (
                row.tenant_id == tenant_id
                and row.category_id == category_id
                and row.version == version
            ):
                return row
        return None

    async def add(self, version: CategorySpecVersion) -> None:
        self._rows[(version.tenant_id, version.id)] = version

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CategorySpecVersion]:
        matches = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.category_id == category_id
        ]
        return sorted(matches, key=lambda row: row.version, reverse=True)
