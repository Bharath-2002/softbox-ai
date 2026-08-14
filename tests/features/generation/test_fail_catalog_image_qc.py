from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.features.generation.fail_catalog_image_qc import FailCatalogImageQc
from app.shared.ids import new_tenant_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[FailCatalogImageQc, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return FailCatalogImageQc(uow_factory, FakeClock(_NOW)), uow_factory


async def test_below_max_attempts_reschedules_the_job() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW, max_attempts=5
    )
    await uow_factory.task_queue.claim(tenant_id, claimed_by="worker", now=_NOW)

    await use_case(tenant_id=tenant_id, job_id=job_id, error="provider down")

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.last_error == "provider down"


async def test_at_max_attempts_the_job_goes_dead() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW, max_attempts=1
    )
    await uow_factory.task_queue.claim(tenant_id, claimed_by="worker", now=_NOW)

    await use_case(tenant_id=tenant_id, job_id=job_id, error="provider down")

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"
