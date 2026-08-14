"""Template storage (D14). Same shape as ``CatalogImageSlotRepository``.

``get_latest_version`` is what the "editing produces a new version" use case
(not built yet) will call to find the version number to increment from — a
template's identity for versioning purposes is
``(tenant_id, catalog_image_slot_id, name)``, not its row id.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.catalog_template import CatalogTemplate
from app.shared.ids import CatalogImageSlotId, CatalogTemplateId, TenantId


class CatalogTemplateRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, template_id: CatalogTemplateId
    ) -> CatalogTemplate | None: ...

    async def add(self, template: CatalogTemplate) -> None: ...

    async def update(self, template: CatalogTemplate) -> None: ...

    async def list_for_catalog_slot(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogTemplate]: ...

    async def get_latest_version(
        self, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId, name: str
    ) -> CatalogTemplate | None: ...
