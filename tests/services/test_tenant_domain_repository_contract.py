"""Runs against both InMemoryTenantDomainRepository and
SqlTenantDomainRepository. No ``SET LOCAL`` needed for the real leg —
``tenant_domains`` carries no RLS (see the migration's module docstring),
so a plain session is enough.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.tenant_domain import TenantDomain
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.tenant_domain_repository import SqlTenantDomainRepository
from app.services.ports.tenant_domain_repository import TenantDomainRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.tenant_domain_repository import InMemoryTenantDomainRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    tenant_domains: TenantDomainRepository
    tenant_id: TenantId


async def _make_real_fixture() -> TenantId:
    tenant_id = new_tenant_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryTenantDomainRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield Context(SqlTenantDomainRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_resolve_by_hostname_returns_none_for_an_unknown_hostname(ctx: Context) -> None:
    assert await ctx.tenant_domains.resolve_by_hostname("unknown.example.com") is None


async def test_add_then_resolve_by_hostname_round_trips(ctx: Context) -> None:
    hostname = f"shop-{ctx.tenant_id.hex[:12]}.example.com"
    domain = TenantDomain.create(ctx.tenant_id, hostname, now=utcnow())

    await ctx.tenant_domains.add(domain)

    resolved = await ctx.tenant_domains.resolve_by_hostname(hostname)
    assert resolved is not None
    assert resolved.tenant_id == ctx.tenant_id


async def test_get_returns_none_for_another_tenants_domain(ctx: Context) -> None:
    hostname = f"shop-{ctx.tenant_id.hex[:12]}.example.com"
    domain = TenantDomain.create(ctx.tenant_id, hostname, now=utcnow())
    await ctx.tenant_domains.add(domain)

    assert await ctx.tenant_domains.get(new_tenant_id(), domain.id) is None


async def test_list_for_tenant_returns_the_domains_just_added(ctx: Context) -> None:
    first = TenantDomain.create(
        ctx.tenant_id, f"shop-a-{ctx.tenant_id.hex[:12]}.example.com", now=utcnow()
    )
    second = TenantDomain.create(
        ctx.tenant_id, f"shop-b-{ctx.tenant_id.hex[:12]}.example.com", now=utcnow()
    )
    await ctx.tenant_domains.add(first)
    await ctx.tenant_domains.add(second)

    listed = await ctx.tenant_domains.list_for_tenant(ctx.tenant_id)

    assert {d.id for d in listed} == {first.id, second.id}
