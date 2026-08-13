"""Runs against both InMemoryIdempotencyRepository and
SqlIdempotencyRepository.

``idempotency_keys`` is RLS-forced (D3) — unlike the other port contracts in
this directory, which cover global tables with no tenant scoping at all, the
"real" leg here must bind ``app.current_tenant`` on its session exactly as
``SqlUnitOfWork`` does, or every call would see zero rows regardless of what
``reserve()`` wrote. Cross-tenant behaviour (the same key used by two
different tenants, RLS rejecting a mismatched write) is a separate concern
from what a single tenant's operations do, and is covered by
``tests/infrastructure/test_idempotency_isolation.py`` instead — this file
stays single-tenant, matching the other contract tests' shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.idempotency_repository import SqlIdempotencyRepository
from app.services.ports.idempotency_repository import IdempotencyRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.idempotency_repository import InMemoryIdempotencyRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    keys: IdempotencyRepository
    tenant_id: TenantId


async def _make_real_tenant() -> TenantId:
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
        yield Context(InMemoryIdempotencyRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlIdempotencyRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_get_on_an_unknown_key_returns_none(ctx: Context) -> None:
    assert await ctx.keys.get(ctx.tenant_id, "never-reserved") is None


async def test_reserve_claims_a_new_key(ctx: Context) -> None:
    claimed = await ctx.keys.reserve(
        ctx.tenant_id, "op-1", request_fingerprint="fp-1", now=utcnow()
    )
    assert claimed is True

    record = await ctx.keys.get(ctx.tenant_id, "op-1")
    assert record is not None
    assert record.request_fingerprint == "fp-1"
    # The gap between reserve() and store_response(): a legitimate
    # in-flight state, not an error.
    assert record.response_status is None
    assert record.response_body is None


async def test_reserving_an_already_claimed_key_does_not_claim_it_again(ctx: Context) -> None:
    first = await ctx.keys.reserve(ctx.tenant_id, "op-2", request_fingerprint="fp-2", now=utcnow())
    second = await ctx.keys.reserve(
        ctx.tenant_id, "op-2", request_fingerprint="a-different-fingerprint", now=utcnow()
    )

    assert first is True
    assert second is False
    # The original fingerprint survives - reserve() never overwrites on conflict.
    record = await ctx.keys.get(ctx.tenant_id, "op-2")
    assert record is not None
    assert record.request_fingerprint == "fp-2"


async def test_store_response_fills_in_the_outcome(ctx: Context) -> None:
    await ctx.keys.reserve(ctx.tenant_id, "op-3", request_fingerprint="fp-3", now=utcnow())

    await ctx.keys.store_response(ctx.tenant_id, "op-3", status=201, body={"id": "abc123"})

    record = await ctx.keys.get(ctx.tenant_id, "op-3")
    assert record is not None
    assert record.response_status == 201
    assert record.response_body == {"id": "abc123"}


async def test_store_response_accepts_no_body(ctx: Context) -> None:
    await ctx.keys.reserve(ctx.tenant_id, "op-4", request_fingerprint="fp-4", now=utcnow())

    await ctx.keys.store_response(ctx.tenant_id, "op-4", status=204, body=None)

    record = await ctx.keys.get(ctx.tenant_id, "op-4")
    assert record is not None
    assert record.response_status == 204
    assert record.response_body is None


async def test_different_keys_for_the_same_tenant_do_not_collide(ctx: Context) -> None:
    first = await ctx.keys.reserve(ctx.tenant_id, "op-5a", request_fingerprint="fp", now=utcnow())
    second = await ctx.keys.reserve(ctx.tenant_id, "op-5b", request_fingerprint="fp", now=utcnow())

    assert first is True
    assert second is True
