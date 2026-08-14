"""Lists the templates one catalog image slot owns."""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CatalogImageSlotId, TenantId


class ListTemplates:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, catalog_image_slot_id: CatalogImageSlotId
    ) -> list[CatalogTemplate]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.catalog_templates.list_for_catalog_slot(
                tenant_id, catalog_image_slot_id
            )
