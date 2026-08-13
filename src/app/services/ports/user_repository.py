"""Users are global — no ``tenant_id`` parameter anywhere on this port."""

from __future__ import annotations

from typing import Protocol

from app.entities.user import User
from app.shared.ids import UserId


class UserRepository(Protocol):
    async def get(self, user_id: UserId) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None:
        """``email`` is matched case-insensitively — the schema's uniqueness
        index is on ``lower(email)``. Callers do not need to lowercase first,
        though ``User.register`` already stores it lowercased."""
        ...

    async def add(self, user: User) -> None: ...

    async def update(self, user: User) -> None: ...
