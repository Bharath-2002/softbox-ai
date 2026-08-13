"""Implements ``app.services.ports.settings_repository.SettingsRepository``.

``== None`` comparisons below compile to ``IS NULL`` — SQLAlchemy's
``Column.__eq__`` special-cases a bare ``None``, so this reads correctly for
both a platform row (``tenant_id`` and ``scope_id`` both ``None``) and a
scoped one without any extra branching.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.setting import Setting, SettingScope
from app.infrastructure.persistence.mapping import settings_table
from app.shared.ids import TenantId


class SqlSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        tenant_id: TenantId | None,
        scope_type: SettingScope,
        scope_id: uuid.UUID | None,
        key: str,
    ) -> Setting | None:
        stmt = select(Setting).where(
            settings_table.c.tenant_id == tenant_id,
            settings_table.c.scope_type == scope_type,
            settings_table.c.scope_id == scope_id,
            settings_table.c.key == key,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, setting: Setting) -> None:
        self._session.add(setting)
        await self._session.flush()

    async def update(self, setting: Setting) -> None:
        await self._session.flush()
