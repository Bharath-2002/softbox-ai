from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.features.system.reap_stuck_task_queue_jobs import ReapStuckTaskQueueJobs
from app.shared.ids import new_tenant_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ReapStuckTaskQueueJobs, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ReapStuckTaskQueueJobs(uow_factory, FakeClock(_NOW)), uow_factory


async def test_reaping_with_nothing_stuck_reaps_zero() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case(new_tenant_id()) == 0


async def test_reaping_requeues_a_job_claimed_long_before_now() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    claimed_at = _NOW - timedelta(minutes=20)
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="a", payload={}, run_at=claimed_at, now=claimed_at
    )
    await uow_factory.task_queue.claim(tenant_id, claimed_by="worker-1", now=claimed_at)

    count = await use_case(tenant_id)

    assert count == 1
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"


async def test_reaping_leaves_a_recently_claimed_job_alone() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    claimed_at = _NOW - timedelta(minutes=1)
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="a", payload={}, run_at=claimed_at, now=claimed_at
    )
    await uow_factory.task_queue.claim(tenant_id, claimed_by="worker-1", now=claimed_at)

    count = await use_case(tenant_id)

    assert count == 0
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "running"
