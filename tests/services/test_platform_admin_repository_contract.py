"""Runs against both InMemoryPlatformAdminRepository and
SqlPlatformAdminRepository.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio

from app.entities.user import User
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.platform_admin_repository import SqlPlatformAdminRepository
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.services.ports.platform_admin_repository import PlatformAdminRepository
from app.services.ports.user_repository import UserRepository
from app.shared.clock import utcnow
from app.shared.ids import UserId, new_user_id
from tests.fakes.platform_admin_repository import InMemoryPlatformAdminRepository
from tests.fakes.user_repository import InMemoryUserRepository
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db


@dataclass
class Context:
    users: UserRepository
    admins: PlatformAdminRepository


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryUserRepository(), InMemoryPlatformAdminRepository())
        return

    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield Context(SqlUserRepository(session), SqlPlatformAdminRepository(session))
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _make_user(ctx: Context) -> UserId:
    user = User.register(f"{new_user_id()}@example.com", now=utcnow())
    await ctx.users.add(user)
    return user.id


async def test_unknown_user_is_not_an_admin(ctx: Context) -> None:
    assert await ctx.admins.is_admin(new_user_id()) is False


async def test_a_regular_user_with_no_grant_is_not_an_admin(ctx: Context) -> None:
    """D4: domain match alone is never sufficient - and neither is merely
    existing as a user. Only an explicit grant counts."""
    user_id = await _make_user(ctx)
    assert await ctx.admins.is_admin(user_id) is False


async def test_grant_then_is_admin(ctx: Context) -> None:
    user_id = await _make_user(ctx)
    granter_id = await _make_user(ctx)

    await ctx.admins.grant(user_id, granted_by=granter_id, now=utcnow())

    assert await ctx.admins.is_admin(user_id) is True


async def test_granting_twice_is_not_an_error(ctx: Context) -> None:
    user_id = await _make_user(ctx)
    granter_id = await _make_user(ctx)

    await ctx.admins.grant(user_id, granted_by=granter_id, now=utcnow())
    await ctx.admins.grant(user_id, granted_by=granter_id, now=utcnow())

    assert await ctx.admins.is_admin(user_id) is True
