"""Runs against both InMemoryTenantMembershipRepository and
SqlTenantMembershipRepository.

The real table has foreign keys to both ``tenants`` and ``users`` — there is
no ``Tenant`` entity/repository yet (out of this chunk's scope), so the real
path seeds a ``tenants`` row directly via the session, the same way
``tests/infrastructure/test_tenant_isolation.py`` does.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.roles import Role
from app.entities.tenant_membership import TenantMembership
from app.entities.user import User
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.tenant_membership_repository import (
    SqlTenantMembershipRepository,
)
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.services.ports.tenant_membership_repository import TenantMembershipRepository
from app.services.ports.user_repository import UserRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, UserId, new_tenant_id, new_user_id
from tests.fakes.tenant_membership_repository import InMemoryTenantMembershipRepository
from tests.fakes.user_repository import InMemoryUserRepository
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db

INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    users: UserRepository
    memberships: TenantMembershipRepository
    session: AsyncSession | None  # None for the fake — nothing to seed a tenant row into


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryUserRepository(), InMemoryTenantMembershipRepository(), None)
        return

    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield Context(SqlUserRepository(session), SqlTenantMembershipRepository(session), session)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _make_tenant(ctx: Context) -> TenantId:
    tenant_id = new_tenant_id()
    if ctx.session is not None:
        await ctx.session.execute(
            INSERT_TENANT, {"id": str(tenant_id), "name": "t", "slug": str(uuid.uuid4())}
        )
    return tenant_id


async def _make_user(ctx: Context) -> UserId:
    user = User.register(f"{new_user_id()}@example.com", now=utcnow())
    await ctx.users.add(user)
    return user.id


async def test_unknown_membership_returns_none(ctx: Context) -> None:
    assert await ctx.memberships.get(new_tenant_id(), new_user_id()) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    tenant_id = await _make_tenant(ctx)
    user_id = await _make_user(ctx)
    membership = TenantMembership.create(tenant_id, user_id, role=Role.ADMIN, now=utcnow())

    await ctx.memberships.add(membership)

    fetched = await ctx.memberships.get(tenant_id, user_id)
    assert fetched is not None
    assert fetched.role == Role.ADMIN


async def test_list_for_user_spans_multiple_tenants(ctx: Context) -> None:
    """The exact query that RLS on this table turned out to make impossible
    for a non-owner role — see the migration's docstring. Two tenants, one
    user, both memberships must come back."""
    user_id = await _make_user(ctx)
    tenant_a = await _make_tenant(ctx)
    tenant_b = await _make_tenant(ctx)
    await ctx.memberships.add(
        TenantMembership.create(tenant_a, user_id, role=Role.OWNER, now=utcnow())
    )
    await ctx.memberships.add(
        TenantMembership.create(tenant_b, user_id, role=Role.VIEWER, now=utcnow())
    )

    memberships = await ctx.memberships.list_for_user(user_id)

    assert {m.tenant_id for m in memberships} == {tenant_a, tenant_b}


async def test_list_for_user_excludes_other_users(ctx: Context) -> None:
    tenant_id = await _make_tenant(ctx)
    user_a = await _make_user(ctx)
    user_b = await _make_user(ctx)
    await ctx.memberships.add(
        TenantMembership.create(tenant_id, user_a, role=Role.OWNER, now=utcnow())
    )
    await ctx.memberships.add(
        TenantMembership.create(tenant_id, user_b, role=Role.VIEWER, now=utcnow())
    )

    only_a = await ctx.memberships.list_for_user(user_a)

    assert [m.user_id for m in only_a] == [user_a]
