"""Hierarchical configuration storage (D16). ``tenant_id`` is explicit and
nullable, unlike every other tenant-scoped port — a platform-level row
belongs to no tenant. A setting's identity is the whole scope tuple
(``tenant_id``, ``scope_type``, ``scope_id``, ``key``), not a bare id, so
``get`` takes all four; ``add``/``update`` follow the same shape every other
repository in this codebase uses.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.entities.setting import Setting, SettingScope
from app.shared.ids import TenantId


class SettingsRepository(Protocol):
    async def get(
        self,
        tenant_id: TenantId | None,
        scope_type: SettingScope,
        scope_id: uuid.UUID | None,
        key: str,
    ) -> Setting | None: ...

    async def add(self, setting: Setting) -> None: ...

    async def update(self, setting: Setting) -> None: ...
