"""``UnitOfWork``'s repository properties (``uow.users``, ``uow.sessions``, ...) —
added when the first use cases needed them (M1 chunk 4 commit 3). See the
port's module docstring for why properties, not constructor-injected repos.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from app.entities.user import User
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_user_id

pytestmark = pytest.mark.db


async def test_repository_properties_are_inaccessible_before_entering() -> None:
    uow = SqlUnitOfWork(session_factory=object(), tenant_id=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="outside its"):
        _ = uow.users


async def test_the_same_property_access_returns_the_same_instance(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    async with owner_uow(None) as uow:
        assert uow.users is uow.users
        assert uow.sessions is uow.sessions


async def test_a_repository_property_writes_through_the_units_own_transaction(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """The point of the property, proven end to end: uow.users is a real,
    working repository sharing this unit of work's transaction, not a
    disconnected stub."""
    user = User.register(f"{new_user_id()}@example.com", now=utcnow())

    async with owner_uow(None) as uow:
        await uow.users.add(user)

    async with owner_uow(None) as uow:
        fetched = await uow.users.get(user.id)

    assert fetched is not None
    assert fetched.email == user.email
