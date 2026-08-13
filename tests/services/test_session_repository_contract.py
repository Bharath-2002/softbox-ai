"""Runs against both InMemorySessionRepository and SqlSessionRepository.

Sessions have a required FK to ``users`` and an optional composite FK to
``tenant_memberships`` when ``tenant_id`` is set (see the migration's
docstring) — every session created here has no active tenant, since these
tests are about the port's behaviour, not the constraint. The constraint
itself is proven in ``tests/infrastructure/test_composite_tenant_fk.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, replace
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.session import Session
from app.entities.user import User
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.session_repository import SqlSessionRepository
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.services.ports.session_repository import SessionRepository
from app.services.ports.user_repository import UserRepository
from app.shared.clock import utcnow
from app.shared.ids import UserId, new_session_id, new_user_id
from tests.fakes.session_repository import InMemorySessionRepository
from tests.fakes.user_repository import InMemoryUserRepository
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db


@dataclass
class Context:
    users: UserRepository
    sessions: SessionRepository


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryUserRepository(), InMemorySessionRepository())
        return

    engine = create_engine(APP_URL)
    session: AsyncSession = create_session_factory(engine)()
    await session.begin()
    try:
        yield Context(SqlUserRepository(session), SqlSessionRepository(session))
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _make_user(ctx: Context) -> UserId:
    user = User.register(f"{new_user_id()}@example.com", now=utcnow())
    await ctx.users.add(user)
    return user.id


def _new_session(user_id: UserId, *, token_hash: str) -> Session:
    now = utcnow()
    return Session(
        id=new_session_id(),
        user_id=user_id,
        tenant_id=None,
        refresh_token_hash=token_hash,
        previous_token_hash=None,
        expires_at=now + timedelta(days=30),
        revoked_at=None,
        created_at=now,
    )


async def test_add_then_get_by_refresh_token_hash_round_trips(ctx: Context) -> None:
    user_id = await _make_user(ctx)
    session = _new_session(user_id, token_hash="hash-1")

    await ctx.sessions.add(session)

    fetched = await ctx.sessions.get_by_refresh_token_hash("hash-1")
    assert fetched is not None
    assert fetched.id == session.id


async def test_unknown_token_hash_returns_none(ctx: Context) -> None:
    assert await ctx.sessions.get_by_refresh_token_hash("nonexistent") is None


async def test_rotation_moves_the_old_hash_to_previous(ctx: Context) -> None:
    user_id = await _make_user(ctx)
    session = _new_session(user_id, token_hash="hash-original")
    await ctx.sessions.add(session)

    session.previous_token_hash = session.refresh_token_hash
    session.refresh_token_hash = "hash-rotated"
    await ctx.sessions.update(session)

    by_new = await ctx.sessions.get_by_refresh_token_hash("hash-rotated")
    by_old_as_previous = await ctx.sessions.get_by_previous_token_hash("hash-original")
    assert by_new is not None and by_new.id == session.id
    assert by_old_as_previous is not None and by_old_as_previous.id == session.id


async def test_revoke_all_for_user_only_touches_that_user(ctx: Context) -> None:
    user_a = await _make_user(ctx)
    user_b = await _make_user(ctx)
    session_a = _new_session(user_a, token_hash="a-hash")
    session_b = _new_session(user_b, token_hash="b-hash")
    await ctx.sessions.add(session_a)
    await ctx.sessions.add(session_b)

    await ctx.sessions.revoke_all_for_user(user_a, now=utcnow())

    refreshed_a = await ctx.sessions.get_by_refresh_token_hash("a-hash")
    refreshed_b = await ctx.sessions.get_by_refresh_token_hash("b-hash")
    assert refreshed_a is not None and refreshed_a.revoked_at is not None
    assert refreshed_b is not None and refreshed_b.revoked_at is None


async def test_is_active_reflects_revocation_and_expiry() -> None:
    now = utcnow()
    active = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash="x",
        previous_token_hash=None,
        expires_at=now + timedelta(days=1),
        revoked_at=None,
        created_at=now,
    )
    assert active.is_active(now=now) is True

    revoked = replace(active, revoked_at=now)
    assert revoked.is_active(now=now) is False

    expired = replace(active, expires_at=now - timedelta(seconds=1))
    assert expired.is_active(now=now) is False
