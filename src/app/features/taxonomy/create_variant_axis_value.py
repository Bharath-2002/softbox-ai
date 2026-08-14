"""Creates one enumerated value for a variant axis (D12) — no
inheritance/override semantics at the value level, unlike a definition's
key (``services/variant_axis.py``'s module docstring), so this is a plain
create with no ancestor-chain lookup.
"""

from __future__ import annotations

from typing import Any

from app.entities.variant_axis import VariantAxisValue
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId, UserId, VariantAxisId


class CreateVariantAxisValue:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        axis_id: VariantAxisId,
        value: str,
        label: str,
        metadata: dict[str, Any] | None = None,
        actor_user_id: UserId,
    ) -> VariantAxisValue:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            axis = await uow.variant_axes.get(tenant_id, axis_id)
            if axis is None:
                raise NotFoundError("Variant axis not found.")

            axis_value = VariantAxisValue.create(
                tenant_id, axis_id, value=value, label=label, now=now, metadata=metadata
            )
            await uow.variant_axis_values.add(axis_value)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="variant_axis_value.created",
                subject_type="variant_axis_value",
                subject_id=axis_value.id,
                before=None,
                after={"value": value, "axis_id": str(axis_id)},
                now=now,
            )

            return axis_value
