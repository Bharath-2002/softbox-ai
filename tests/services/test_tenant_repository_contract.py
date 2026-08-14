"""Runs against both InMemoryTenantRepository and SqlTenantRepository.
``tenants`` carries no RLS (D4) — this is the one contract test in this
directory whose "real" leg needs no ``SET LOCAL app.current_tenant`` at all,
since the query is a legitimate cross-tenant read.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.tenant_repository import SqlTenantRepository
from app.services.ports.tenant_repository import TenantRepository
from app.shared.ids import new_tenant_id
from tests.fakes.tenant_repository import InMemoryTenantRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, :status, now(), now())"
)


@pytest_asyncio.fixture(params=["fake", "real"])
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[TenantRepository]:
    if request.param == "fake":
        yield InMemoryTenantRepository()
        return

    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    try:
        yield SqlTenantRepository(session)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def _insert_real_tenant(*, status: str) -> None:
    tenant_id = new_tenant_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {
            "id": str(tenant_id),
            "name": f"tenant-{tenant_id.hex[:8]}",
            "slug": str(tenant_id),
            "status": status,
        },
    )
    await session.commit()
    await session.close()
    await engine.dispose()


async def test_list_active_only_returns_active_tenants(
    repo: TenantRepository, request: pytest.FixtureRequest
) -> None:
    if isinstance(repo, InMemoryTenantRepository):
        active_id = new_tenant_id()
        repo.active_tenant_ids = [active_id]
        assert await repo.list_active() == [active_id]
        return

    before = set(await repo.list_active())
    await _insert_real_tenant(status="active")
    await _insert_real_tenant(status="suspended")

    after = set(await repo.list_active())

    assert len(after - before) == 1
