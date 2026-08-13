from __future__ import annotations

from app.entities.user import User
from app.shared.ids import UserId


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._rows: dict[UserId, User] = {}

    async def get(self, user_id: UserId) -> User | None:
        return self._rows.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        needle = email.strip().lower()
        return next((u for u in self._rows.values() if u.email.lower() == needle), None)

    async def add(self, user: User) -> None:
        self._rows[user.id] = user

    async def update(self, user: User) -> None:
        self._rows[user.id] = user
