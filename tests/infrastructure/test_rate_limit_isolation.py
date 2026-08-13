"""Tenant isolation for ``rate_limit_windows``, proven against the real
``SqlRateLimiter`` — which binds its own tenant context per call rather than
sharing a caller-managed ``UnitOfWork`` (see the port's module docstring for
why this adapter's lifecycle differs from the repository adapters).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.rate_limiter import SqlRateLimiter
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant() -> TenantId:
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


async def test_the_same_bucket_name_is_independent_per_tenant() -> None:
    tenant_a = await _make_tenant()
    tenant_b = await _make_tenant()
    engine = create_engine(APP_URL)
    try:
        limiter = SqlRateLimiter(create_session_factory(engine))
        window = timedelta(seconds=60)
        now = utcnow()

        await limiter.allow(tenant_a, "shared-bucket", limit=1, window=window, now=now)
        allowed_for_b = await limiter.allow(
            tenant_b, "shared-bucket", limit=1, window=window, now=now
        )

        assert allowed_for_b is True
    finally:
        await engine.dispose()


async def test_exhausting_tenant_as_limit_does_not_affect_tenant_b() -> None:
    tenant_a = await _make_tenant()
    tenant_b = await _make_tenant()
    engine = create_engine(APP_URL)
    try:
        limiter = SqlRateLimiter(create_session_factory(engine))
        window = timedelta(seconds=60)
        now = utcnow()

        await limiter.allow(tenant_a, "op", limit=1, window=window, now=now)
        tenant_a_rejected = await limiter.allow(tenant_a, "op", limit=1, window=window, now=now)
        tenant_b_allowed = await limiter.allow(tenant_b, "op", limit=1, window=window, now=now)

        assert tenant_a_rejected is False
        assert tenant_b_allowed is True
    finally:
        await engine.dispose()


async def test_force_rls_applies_even_to_the_owner_role() -> None:
    tenant_id = await _make_tenant()
    engine = create_engine(APP_URL)
    try:
        limiter = SqlRateLimiter(create_session_factory(engine))
        await limiter.allow(tenant_id, "op", limit=5, window=timedelta(seconds=60), now=utcnow())
    finally:
        await engine.dispose()

    owner_engine = create_engine(OWNER_URL)
    try:
        owner_session_factory = create_session_factory(owner_engine)
        async with owner_session_factory() as session:
            await session.begin()
            result = await session.execute(text("SELECT count(*) FROM rate_limit_windows"))
            count = result.scalar_one()
            await session.rollback()
    finally:
        await owner_engine.dispose()

    assert count == 0
