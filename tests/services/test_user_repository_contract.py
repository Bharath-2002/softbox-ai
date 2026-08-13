"""Runs against both InMemoryUserRepository and SqlUserRepository — the same
assertions, so the fake cannot drift into a lie about the real adapter's
behaviour.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.entities.user import User
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.services.ports.user_repository import UserRepository
from app.shared.clock import utcnow
from app.shared.ids import new_user_id
from tests.fakes.user_repository import InMemoryUserRepository
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db


@pytest_asyncio.fixture(params=["fake", "real"])
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[UserRepository]:
    if request.param == "fake":
        yield InMemoryUserRepository()
        return

    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield SqlUserRepository(session)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _new_user(email: str = "person@example.com") -> User:
    return User.register(email, now=utcnow())


async def test_unknown_id_returns_none(repo: UserRepository) -> None:
    assert await repo.get(new_user_id()) is None


async def test_add_then_get_round_trips(repo: UserRepository) -> None:
    user = _new_user()
    await repo.add(user)

    fetched = await repo.get(user.id)

    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.email == "person@example.com"


async def test_get_by_email_is_case_insensitive(repo: UserRepository) -> None:
    user = _new_user("Person@Example.com")
    await repo.add(user)

    # Stored lowercased by User.register; looked up with a different case.
    fetched = await repo.get_by_email("PERSON@example.COM")

    assert fetched is not None
    assert fetched.id == user.id


async def test_get_by_email_unknown_returns_none(repo: UserRepository) -> None:
    assert await repo.get_by_email("nobody@example.com") is None


async def test_update_persists_mutated_fields(repo: UserRepository) -> None:
    user = _new_user()
    await repo.add(user)

    user.display_name = "Updated Name"
    user.email_verified = True
    await repo.update(user)

    fetched = await repo.get(user.id)
    assert fetched is not None
    assert fetched.display_name == "Updated Name"
    assert fetched.email_verified is True
