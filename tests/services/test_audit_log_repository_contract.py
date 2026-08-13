"""Runs against both InMemoryAuditLogRepository and SqlAuditLogRepository.

``audit_log`` is RLS-forced (D3, proven generically in
``test_tenant_isolation.py`` via raw SQL since chunk 3) — same fixture shape
as the idempotency and rate-limit contract tests: the "real" leg binds
``app.current_tenant`` on its session before running anything. Cross-tenant
behaviour through the repository (as opposed to raw SQL) lives in
``tests/infrastructure/test_audit_log_isolation.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.audit_log_repository import SqlAuditLogRepository
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.audit_log_repository import AuditLogRepository
from app.shared.ids import TenantId, UserId, new_tenant_id, new_user_id
from tests.fakes.audit_log_repository import InMemoryAuditLogRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    audit_log: AuditLogRepository
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
        yield Context(InMemoryAuditLogRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlAuditLogRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _actor() -> UserId:
    return new_user_id()


async def test_a_recorded_entry_is_listed_back(ctx: Context) -> None:
    actor = _actor()
    subject_id = uuid4()

    await ctx.audit_log.record(
        ctx.tenant_id,
        actor_user_id=actor,
        action="product.updated",
        subject_type="product",
        subject_id=subject_id,
        before={"price": 100},
        after={"price": 120},
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    entries = await ctx.audit_log.list_for_subject(ctx.tenant_id, "product", subject_id)
    assert len(entries) == 1
    assert entries[0].action == "product.updated"
    assert entries[0].actor_user_id == actor
    assert entries[0].before == {"price": 100}
    assert entries[0].after == {"price": 120}


async def test_a_system_action_with_no_actor_is_recorded(ctx: Context) -> None:
    subject_id = uuid4()

    await ctx.audit_log.record(
        ctx.tenant_id,
        actor_user_id=None,
        action="product.auto_archived",
        subject_type="product",
        subject_id=subject_id,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    entries = await ctx.audit_log.list_for_subject(ctx.tenant_id, "product", subject_id)
    assert entries[0].actor_user_id is None


async def test_entries_for_an_unrelated_subject_are_not_returned(ctx: Context) -> None:
    subject_id = uuid4()
    other_subject_id = uuid4()
    await ctx.audit_log.record(
        ctx.tenant_id,
        actor_user_id=_actor(),
        action="product.updated",
        subject_type="product",
        subject_id=other_subject_id,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )

    entries = await ctx.audit_log.list_for_subject(ctx.tenant_id, "product", subject_id)

    assert entries == []


async def test_entries_are_returned_newest_first(ctx: Context) -> None:
    subject_id = uuid4()
    await ctx.audit_log.record(
        ctx.tenant_id,
        actor_user_id=_actor(),
        action="product.created",
        subject_type="product",
        subject_id=subject_id,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ctx.audit_log.record(
        ctx.tenant_id,
        actor_user_id=_actor(),
        action="product.updated",
        subject_type="product",
        subject_id=subject_id,
        now=datetime(2026, 1, 2, tzinfo=UTC),
    )

    entries = await ctx.audit_log.list_for_subject(ctx.tenant_id, "product", subject_id)

    assert [entry.action for entry in entries] == ["product.updated", "product.created"]
