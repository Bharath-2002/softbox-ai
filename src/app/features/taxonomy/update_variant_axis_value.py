"""Edits a variant axis value's label/metadata. ``value`` itself is not
editable — it is what a product's variant actually stores, so it carries
the same referential weight a definition's ``key`` does.
"""

from __future__ import annotations

from typing import Any

from app.entities.variant_axis import VariantAxisValue
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId, UserId, VariantAxisValueId


class UpdateVariantAxisValue:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        value_id: VariantAxisValueId,
        label: str,
        metadata: dict[str, Any],
        actor_user_id: UserId,
    ) -> VariantAxisValue:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            axis_value = await uow.variant_axis_values.get(tenant_id, value_id)
            if axis_value is None:
                raise NotFoundError("Variant axis value not found.")

            before = {"label": axis_value.label}

            axis_value.label = label
            axis_value.metadata = metadata
            axis_value.updated_at = now
            await uow.variant_axis_values.update(axis_value)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="variant_axis_value.updated",
                subject_type="variant_axis_value",
                subject_id=value_id,
                before=before,
                after={"label": label},
                now=now,
            )

            return axis_value
