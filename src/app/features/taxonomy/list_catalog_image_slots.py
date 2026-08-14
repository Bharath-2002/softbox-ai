"""Lists the catalog image slots one category owns directly."""

from __future__ import annotations

from app.entities.image_slots import CatalogImageSlot
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId


class ListCatalogImageSlots:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CatalogImageSlot]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.catalog_image_slots.list_for_category(tenant_id, category_id)
