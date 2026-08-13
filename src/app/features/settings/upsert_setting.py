"""Writes one setting (D16) — an upsert, since a caller re-setting a key
they already set should replace the value, not create a second row (the
migration's partial unique indexes would reject a duplicate anyway).

``tenant_id`` doubles as both the row's own tenant and the transaction's
bound tenant (``uow_factory(tenant_id)``) — for a platform-scoped write that
is ``None`` both times, which is exactly what the migration's RLS policy
requires: a platform-wide row can only be written by a platform-plane
session with no tenant bound at all.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.entities.setting import Setting, SettingScope
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId


class UpsertSetting:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId | None,
        scope_type: SettingScope,
        scope_id: uuid.UUID | None,
        key: str,
        value: Any,
    ) -> Setting:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            existing = await uow.settings.get(tenant_id, scope_type, scope_id, key)
            if existing is not None:
                existing.value = value
                existing.updated_at = now
                await uow.settings.update(existing)
                return existing

            setting = Setting.create(
                scope_type=scope_type,
                tenant_id=tenant_id,
                scope_id=scope_id,
                key=key,
                value=value,
                now=now,
            )
            await uow.settings.add(setting)
            return setting
