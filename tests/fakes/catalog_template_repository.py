from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.shared.ids import CatalogImageSlotId, CatalogTemplateId, TenantId


class InMemoryCatalogTemplateRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, CatalogTemplateId], CatalogTemplate] = {}

    async def get(
        self, tenant_id: TenantId, template_id: CatalogTemplateId
    ) -> CatalogTemplate | None:
        return self._rows.get((tenant_id, template_id))

    async def add(self, template: CatalogTemplate) -> None:
        self._rows[(template.tenant_id, template.id)] = template

    async def update(self, template: CatalogTemplate) -> None:
        self._rows[(template.tenant_id, template.id)] = template

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogTemplate]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.catalog_image_slot_id == catalog_image_slot_id
        ]
        return sorted(matches, key=lambda row: row.position)

    async def get_latest_version(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId, name: str
    ) -> CatalogTemplate | None:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id
            and row.catalog_image_slot_id == catalog_image_slot_id
            and row.name == name
        ]
        if not matches:
            return None
        return max(matches, key=lambda row: row.version)
