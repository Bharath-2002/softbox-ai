"""Implements ``app.services.ports.platform_admin_repository.PlatformAdminRepository``.

Core queries against ``platform_admins_table`` directly — there is no
``PlatformAdmin`` entity to hydrate (see the mapping module), just a grant to
check or record.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import platform_admins_table
from app.shared.ids import UserId


class SqlPlatformAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_admin(self, user_id: UserId) -> bool:
        stmt = select(platform_admins_table.c.user_id).where(
            platform_admins_table.c.user_id == user_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def grant(self, user_id: UserId, *, granted_by: UserId, now: datetime) -> None:
        # ON CONFLICT DO NOTHING: granting an existing admin again is a no-op,
        # not an error - idempotent by construction rather than requiring the
        # caller to check first.
        stmt = (
            insert(platform_admins_table)
            .values(user_id=user_id, granted_by=granted_by, granted_at=now)
            .on_conflict_do_nothing(index_elements=[platform_admins_table.c.user_id])
        )
        await self._session.execute(stmt)
        await self._session.flush()
