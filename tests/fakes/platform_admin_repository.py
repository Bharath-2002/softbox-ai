from __future__ import annotations

from datetime import datetime

from app.shared.ids import UserId


class InMemoryPlatformAdminRepository:
    def __init__(self) -> None:
        self._admins: set[UserId] = set()

    async def is_admin(self, user_id: UserId) -> bool:
        return user_id in self._admins

    async def grant(self, user_id: UserId, *, granted_by: UserId, now: datetime) -> None:
        self._admins.add(user_id)
