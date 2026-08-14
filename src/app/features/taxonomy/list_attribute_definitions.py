"""Lists the attribute definitions one category owns directly — not the
inherited, resolved view (that is ``SpecSnapshotBuilder``'s job at publish
time). The editor needs to see and edit exactly what a category itself
defines.
"""

from __future__ import annotations

from app.entities.attribute_definition import AttributeDefinition
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId


class ListAttributeDefinitions:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, category_id: CategoryId
    ) -> list[AttributeDefinition]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.attribute_definitions.list_for_category(tenant_id, category_id)
