"""Edits a variant axis's non-referential fields. ``key`` is not editable
(D15's rename-forbidden case)."""

from __future__ import annotations

from app.entities.variant_axis import VariantAxis
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId, UserId, VariantAxisId


class UpdateVariantAxis:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        axis_id: VariantAxisId,
        label: str,
        affects_imagery: bool,
        position: int,
        actor_user_id: UserId,
    ) -> VariantAxis:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            axis = await uow.variant_axes.get(tenant_id, axis_id)
            if axis is None:
                raise NotFoundError("Variant axis not found.")

            before = {"label": axis.label, "affects_imagery": axis.affects_imagery}

            axis.label = label
            axis.affects_imagery = affects_imagery
            axis.position = position
            axis.updated_at = now
            await uow.variant_axes.update(axis)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="variant_axis.updated",
                subject_type="variant_axis",
                subject_id=axis_id,
                before=before,
                after={"label": label, "affects_imagery": affects_imagery},
                now=now,
            )

            return axis
