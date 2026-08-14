"""Lists an axis's enumerated values."""

from __future__ import annotations

from app.entities.variant_axis import VariantAxisValue
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import TenantId, VariantAxisId


class ListVariantAxisValues:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, axis_id: VariantAxisId
    ) -> list[VariantAxisValue]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.variant_axis_values.list_for_axis(tenant_id, axis_id)
