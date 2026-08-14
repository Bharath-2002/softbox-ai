from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.generation_item import GenerationItem
from app.features.generation.fail_generation_item_render import FailGenerationItemRender
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_generation_item_id,
    new_generation_request_id,
    new_tenant_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[FailGenerationItemRender, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return FailGenerationItemRender(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_running_item(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, *, max_attempts: int = 5
) -> tuple[GenerationItem, object]:
    item = GenerationItem.create(
        tenant_id,
        new_generation_request_id(),
        new_catalog_image_slot_id(),
        new_catalog_template_id(),
        attempt_no=1,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={},
        seed=1,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=[],
        now=_NOW,
    )
    item.mark_running()
    await uow_factory.generation_items.add(item)

    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW, max_attempts=max_attempts
    )
    await uow_factory.task_queue.claim(tenant_id, claimed_by="worker", now=_NOW)

    return item, job_id


async def test_below_max_attempts_marks_the_item_failed_not_dead() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    item, job_id = await _seed_running_item(uow_factory, tenant_id, max_attempts=5)

    result = await use_case(
        tenant_id=tenant_id,
        item_id=item.id,
        job_id=job_id,
        error_code="ProviderTimeout",
        error_detail="timed out after 30s",
    )

    assert result.status.value == "failed"
    assert result.error_code == "ProviderTimeout"
    assert result.error_detail == "timed out after 30s"

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"


async def test_at_max_attempts_the_item_follows_the_job_into_dead() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    item, job_id = await _seed_running_item(uow_factory, tenant_id, max_attempts=1)

    result = await use_case(
        tenant_id=tenant_id, item_id=item.id, job_id=job_id, error_code="x", error_detail="boom"
    )

    assert result.status.value == "dead"
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"


async def test_an_unknown_item_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW
    )

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            item_id=new_generation_item_id(),
            job_id=job_id,
            error_code="x",
            error_detail="x",
        )
