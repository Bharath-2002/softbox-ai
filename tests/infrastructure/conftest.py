"""Fixtures for tests against a real Postgres.

Local development and CI both point these at a `softbox_test` database
provisioned by ``scripts/bootstrap_local_db.sh`` with migrations already
applied — one code path, no testcontainers, per the M1 decision to drop
Docker from this project (CHECKLIST.md, M1 Project setup).

These fixtures deliberately do not skip when Postgres is unavailable. A
skipped isolation test is a silent pass for the exact property this suite
exists to guarantee.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.ids import TenantId

OWNER_URL = os.environ.get(
    "SOFTBOX_TEST_OWNER_DATABASE_URL",
    "postgresql+asyncpg://softbox_owner:softbox_owner_dev_only@localhost:5432/softbox_test",
)
APP_URL = os.environ.get(
    "SOFTBOX_TEST_APP_DATABASE_URL",
    "postgresql+asyncpg://softbox_app:softbox_app_dev_only@localhost:5432/softbox_test",
)


@pytest_asyncio.fixture
async def owner_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(OWNER_URL)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def app_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_engine(APP_URL)
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def owner_uow(
    owner_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[TenantId | None], SqlUnitOfWork]:
    return lambda tenant_id=None: SqlUnitOfWork(owner_session_factory, tenant_id)


@pytest.fixture
def app_uow(
    app_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[TenantId | None], SqlUnitOfWork]:
    return lambda tenant_id=None: SqlUnitOfWork(app_session_factory, tenant_id)
