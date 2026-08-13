from __future__ import annotations

import uuid

from app.entities.setting import Setting, SettingScope
from app.shared.ids import TenantId

_Key = tuple[TenantId | None, SettingScope, uuid.UUID | None, str]


class InMemorySettingsRepository:
    def __init__(self) -> None:
        self._rows: dict[_Key, Setting] = {}

    def _key(self, setting: Setting) -> _Key:
        return (setting.tenant_id, setting.scope_type, setting.scope_id, setting.key)

    async def get(
        self,
        tenant_id: TenantId | None,
        scope_type: SettingScope,
        scope_id: uuid.UUID | None,
        key: str,
    ) -> Setting | None:
        return self._rows.get((tenant_id, scope_type, scope_id, key))

    async def add(self, setting: Setting) -> None:
        self._rows[self._key(setting)] = setting

    async def update(self, setting: Setting) -> None:
        self._rows[self._key(setting)] = setting
