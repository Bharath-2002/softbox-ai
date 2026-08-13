"""Runs against both InMemoryIdentityRepository and SqlIdentityRepository.

Every identity references a user via a real foreign key, so each test case
creates one through the matching ``UserRepository`` first — for the real
adapter this is load-bearing (the insert would fail otherwise); for the fake
it costs nothing and keeps both paths exercising the same setup.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio

from app.entities.identity import Identity
from app.entities.user import User
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.identity_repository import SqlIdentityRepository
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.services.ports.identity_repository import IdentityRepository
from app.services.ports.user_repository import UserRepository
from app.shared.clock import utcnow
from app.shared.ids import UserId
from tests.fakes.identity_repository import InMemoryIdentityRepository
from tests.fakes.user_repository import InMemoryUserRepository
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db


@dataclass
class Context:
    users: UserRepository
    identities: IdentityRepository


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryUserRepository(), InMemoryIdentityRepository())
        return

    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield Context(SqlUserRepository(session), SqlIdentityRepository(session))
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _make_user(ctx: Context) -> UserId:
    user = User.register("person@example.com", now=utcnow())
    await ctx.users.add(user)
    return user.id


async def test_unknown_provider_subject_returns_none(ctx: Context) -> None:
    assert (
        await ctx.identities.get_by_provider_subject("google", "https://accounts.google.com", "abc")
        is None
    )


async def test_add_then_lookup_round_trips(ctx: Context) -> None:
    user_id = await _make_user(ctx)
    identity = Identity.create(
        user_id,
        provider="google",
        issuer="https://accounts.google.com",
        subject="sub-123",
        raw_claims={"email": "person@example.com"},
        now=utcnow(),
    )
    await ctx.identities.add(identity)

    fetched = await ctx.identities.get_by_provider_subject(
        "google", "https://accounts.google.com", "sub-123"
    )

    assert fetched is not None
    assert fetched.user_id == user_id


async def test_same_subject_different_issuer_does_not_collide(ctx: Context) -> None:
    """The exact case advisor flagged: `sub` is only unique per issuer."""
    user_a = await _make_user(ctx)
    identity_a = Identity.create(
        user_a,
        provider="microsoft",
        issuer="https://login.microsoftonline.com/tenant-a",
        subject="same-subject",
        raw_claims={},
        now=utcnow(),
    )
    await ctx.identities.add(identity_a)

    # A different Entra tenant handing out the same subject value.
    found_under_other_issuer = await ctx.identities.get_by_provider_subject(
        "microsoft", "https://login.microsoftonline.com/tenant-b", "same-subject"
    )

    assert found_under_other_issuer is None
