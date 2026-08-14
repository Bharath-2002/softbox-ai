from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.features.content.fail_content_draft_generation import FailContentDraftGeneration
from app.shared.ids import new_tenant_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[FailContentDraftGeneration, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return FailContentDraftGeneration(uow_factory, FakeClock(_NOW)), uow_factory


async def test_fails_the_job_with_the_provider_error() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="content_draft.generate_requested", payload={}, run_at=_NOW, now=_NOW
    )

    await use_case(
        tenant_id=tenant_id,
        job_id=job_id,
        error_code="ProviderTimeout",
        error_detail="upstream timed out",
    )

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"
    assert job.last_error == "ProviderTimeout: upstream timed out"
