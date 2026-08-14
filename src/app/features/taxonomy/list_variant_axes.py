"""Lists the variant axes one category owns directly (not the resolved,
inherited view)."""

from __future__ import annotations

from app.entities.variant_axis import VariantAxis
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import CategoryId, TenantId


class ListVariantAxes:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, tenant_id: TenantId, category_id: CategoryId) -> list[VariantAxis]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.variant_axes.list_for_category(tenant_id, category_id)
