"""Implements ``app.services.ports.session_repository.SessionRepository``.

Filters use ``sessions_table.c.*``, not the mapped class's own attributes —
see ``user_repository.py`` for why.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.session import Session
from app.infrastructure.persistence.mapping import sessions_table
from app.shared.ids import UserId


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: Session) -> None:
        self._session.add(session)
        await self._session.flush()

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        stmt = select(Session).where(sessions_table.c.refresh_token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_previous_token_hash(self, token_hash: str) -> Session | None:
        stmt = select(Session).where(sessions_table.c.previous_token_hash == token_hash)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def update(self, session: Session) -> None:
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime) -> None:
        stmt = (
            update(Session)
            .where(sessions_table.c.user_id == user_id, sessions_table.c.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await self._session.execute(stmt)
        await self._session.flush()
