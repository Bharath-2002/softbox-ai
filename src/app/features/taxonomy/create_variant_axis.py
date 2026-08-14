"""Creates a variant axis (D12) on a category. Same no-uniqueness-check
reasoning as ``CreateAttributeDefinition`` — a descendant may override an
inherited axis key.
"""

from __future__ import annotations

from app.entities.variant_axis import VariantAxis
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateVariantAxis:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        key: str,
        label: str,
        affects_imagery: bool,
        position: int = 0,
        actor_user_id: UserId,
    ) -> VariantAxis:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            axis = VariantAxis.create(
                tenant_id,
                category_id,
                key=key,
                label=label,
                affects_imagery=affects_imagery,
                now=now,
                position=position,
            )
            await uow.variant_axes.add(axis)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="variant_axis.created",
                subject_type="variant_axis",
                subject_id=axis.id,
                before=None,
                after={"key": key, "category_id": str(category_id)},
                now=now,
            )

            return axis
