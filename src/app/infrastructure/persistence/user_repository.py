"""Implements ``app.services.ports.user_repository.UserRepository``.

Filters are built from ``users_table.c.*`` (the Core ``Table``, typed and
unambiguous), not the mapped entity class's own attributes (``User.email``).
The latter reads more naturally but mypy cannot type it: imperative mapping
binds a plain dataclass, and SQLAlchemy's mypy plugin only understands
class-level query attributes on declarative ``Mapped[...]`` classes. Filtering
through the table sidesteps the gap entirely while ``select(User)`` still
returns fully hydrated entity instances.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.user import User
from app.infrastructure.persistence.mapping import users_table
from app.shared.ids import UserId


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(users_table.c.email) == email.strip().lower())
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, user: User) -> None:
        self._session.add(user)
        await self._session.flush()

    async def update(self, user: User) -> None:
        # A no-op beyond the flush: `user` is already the identity-mapped
        # instance from `get`, so mutating its attributes is the update.
        # Kept as an explicit method on the port so callers state intent and
        # the SQL is not the only place that knows attribute mutation is
        # sufficient here.
        await self._session.flush()
