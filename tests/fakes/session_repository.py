from __future__ import annotations

from datetime import datetime

from app.entities.session import Session
from app.shared.ids import SessionId, UserId


class InMemorySessionRepository:
    def __init__(self) -> None:
        self._rows: dict[SessionId, Session] = {}

    async def add(self, session: Session) -> None:
        self._rows[session.id] = session

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        return next((s for s in self._rows.values() if s.refresh_token_hash == token_hash), None)

    async def get_by_previous_token_hash(self, token_hash: str) -> Session | None:
        return next((s for s in self._rows.values() if s.previous_token_hash == token_hash), None)

    async def update(self, session: Session) -> None:
        self._rows[session.id] = session

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime) -> None:
        for session in self._rows.values():
            if session.user_id == user_id and session.revoked_at is None:
                session.revoked_at = now
