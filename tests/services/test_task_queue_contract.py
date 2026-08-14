"""Runs against both InMemoryTaskQueue and SqlTaskQueue. ``task_queue_jobs``
depends on nothing but ``tenants``, same shape as
``test_outbox_event_repository_contract.py``.

The concurrency property SKIP LOCKED exists for — two claimers never get the
same job — cannot be expressed with this file's single-session-per-context
fixture; that lives in
``tests/infrastructure/test_task_queue_concurrency.py`` instead, against
real Postgres only, using genuinely separate connections.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.task_queue import SqlTaskQueue
from app.services.ports.task_queue import TaskQueue
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.task_queue import InMemoryTaskQueue
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    jobs: TaskQueue
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
        yield Context(InMemoryTaskQueue(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlTaskQueue(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_claim_returns_none_when_nothing_is_pending(ctx: Context) -> None:
    assert await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=utcnow()) is None


async def test_claim_returns_a_due_pending_job_and_marks_it_running(ctx: Context) -> None:
    job_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="generation.step", payload={"n": 1}, run_at=utcnow(), now=utcnow()
    )

    claimed = await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=utcnow())

    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.status == "running"
    assert claimed.claimed_by == "worker-1"


async def test_claim_does_not_return_a_job_scheduled_in_the_future(ctx: Context) -> None:
    now = utcnow()
    await ctx.jobs.enqueue(
        ctx.tenant_id,
        job_type="generation.step",
        payload={},
        run_at=now + timedelta(hours=1),
        now=now,
    )

    assert await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now) is None


async def test_claim_does_not_return_an_already_running_job(ctx: Context) -> None:
    now = utcnow()
    await ctx.jobs.enqueue(ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now)
    first = await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)
    assert first is not None

    second = await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-2", now=now)

    assert second is None


async def test_complete_marks_the_job_succeeded(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now)
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    await ctx.jobs.complete(ctx.tenant_id, job_id, now=now)

    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "succeeded"


async def test_fail_below_max_attempts_reschedules_as_pending(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now, max_attempts=5
    )
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    result = await ctx.jobs.fail(ctx.tenant_id, job_id, error="boom", now=now)

    assert result == "pending"
    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.attempts == 1
    assert job.last_error == "boom"
    assert job.run_at >= now


async def test_fail_at_max_attempts_transitions_to_dead(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now, max_attempts=1
    )
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    result = await ctx.jobs.fail(ctx.tenant_id, job_id, error="boom", now=now)

    assert result == "dead"
    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"
    assert job.attempts == 1
    assert job.last_error == "boom"


async def test_fail_on_an_unknown_job_raises(ctx: Context) -> None:
    with pytest.raises(ValueError):
        await ctx.jobs.fail(ctx.tenant_id, uuid.uuid4(), error="boom", now=utcnow())


async def test_claim_with_job_type_ignores_a_due_job_of_a_different_type(ctx: Context) -> None:
    now = utcnow()
    await ctx.jobs.enqueue(ctx.tenant_id, job_type="other.type", payload={}, run_at=now, now=now)

    claimed = await ctx.jobs.claim(
        ctx.tenant_id, claimed_by="worker-1", job_type="generation.step", now=now
    )

    assert claimed is None


async def test_claim_with_job_type_returns_a_matching_due_job(ctx: Context) -> None:
    now = utcnow()
    await ctx.jobs.enqueue(ctx.tenant_id, job_type="other.type", payload={}, run_at=now, now=now)
    job_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="generation.step", payload={}, run_at=now, now=now
    )

    claimed = await ctx.jobs.claim(
        ctx.tenant_id, claimed_by="worker-1", job_type="generation.step", now=now
    )

    assert claimed is not None
    assert claimed.id == job_id


async def test_get_on_an_unknown_job_returns_none(ctx: Context) -> None:
    assert await ctx.jobs.get(ctx.tenant_id, uuid.uuid4()) is None


async def test_reap_stuck_requeues_a_job_claimed_before_the_threshold(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now)
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    reaped_at = now + timedelta(minutes=15)
    count = await ctx.jobs.reap_stuck(
        ctx.tenant_id, claimed_before=now + timedelta(minutes=10), now=reaped_at
    )

    assert count == 1
    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.attempts == 1
    assert job.last_error is not None
    assert job.run_at >= reaped_at


async def test_reap_stuck_ignores_a_job_claimed_after_the_threshold(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now)
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    count = await ctx.jobs.reap_stuck(
        ctx.tenant_id, claimed_before=now - timedelta(minutes=10), now=now
    )

    assert count == 0
    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "running"


async def test_reap_stuck_ignores_pending_and_succeeded_jobs(ctx: Context) -> None:
    now = utcnow()
    succeeded_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now
    )
    pending_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="a", payload={}, run_at=now + timedelta(minutes=1), now=now
    )
    claimed = await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)
    assert claimed is not None
    assert claimed.id == succeeded_id
    await ctx.jobs.complete(ctx.tenant_id, succeeded_id, now=now)

    count = await ctx.jobs.reap_stuck(
        ctx.tenant_id, claimed_before=now + timedelta(hours=1), now=now
    )

    assert count == 0
    pending = await ctx.jobs.get(ctx.tenant_id, pending_id)
    assert pending is not None
    assert pending.status == "pending"
    succeeded = await ctx.jobs.get(ctx.tenant_id, succeeded_id)
    assert succeeded is not None
    assert succeeded.status == "succeeded"


async def test_reap_stuck_at_max_attempts_transitions_to_dead(ctx: Context) -> None:
    now = utcnow()
    job_id = await ctx.jobs.enqueue(
        ctx.tenant_id, job_type="a", payload={}, run_at=now, now=now, max_attempts=1
    )
    await ctx.jobs.claim(ctx.tenant_id, claimed_by="worker-1", now=now)

    count = await ctx.jobs.reap_stuck(
        ctx.tenant_id, claimed_before=now + timedelta(minutes=10), now=now + timedelta(minutes=15)
    )

    assert count == 1
    job = await ctx.jobs.get(ctx.tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"
