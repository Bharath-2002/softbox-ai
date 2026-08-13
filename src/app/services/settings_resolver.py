"""D16's read path: ``platform -> tenant -> category`` (root to leaf),
most specific wins. ``product`` is the fourth level D16 names but has no
table to resolve against until M4 — adding it later only means widening
``resolve``'s signature, not restructuring the walk.

Same shape as ``PrincipalResolver``/``SpecResolver``: ports injected
directly, not a ``UnitOfWork``, so this opens no transaction of its own.
"""

from __future__ import annotations

from typing import Any

from app.entities.setting import SettingScope
from app.services.ports.category_repository import CategoryRepository
from app.services.ports.settings_repository import SettingsRepository
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId


class SettingsResolver:
    def __init__(self, settings: SettingsRepository, categories: CategoryRepository) -> None:
        self._settings = settings
        self._categories = categories

    async def resolve(
        self, tenant_id: TenantId, key: str, *, category_id: CategoryId | None = None
    ) -> Any | None:
        resolved: Any | None = None

        platform_setting = await self._settings.get(None, SettingScope.PLATFORM, None, key)
        if platform_setting is not None:
            resolved = platform_setting.value

        tenant_setting = await self._settings.get(tenant_id, SettingScope.TENANT, None, key)
        if tenant_setting is not None:
            resolved = tenant_setting.value

        if category_id is not None:
            category = await self._categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")
            for ancestor_id in category.ancestor_ids():
                category_setting = await self._settings.get(
                    tenant_id, SettingScope.CATEGORY, ancestor_id, key
                )
                if category_setting is not None:
                    resolved = category_setting.value

        return resolved
