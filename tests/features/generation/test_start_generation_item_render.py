from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.asset import Asset, AssetKind
from app.entities.generation_item import GenerationItem
from app.features.generation.start_generation_item_render import (
    JOB_TYPE,
    StartGenerationItemRender,
)
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_generation_item_id,
    new_generation_request_id,
    new_tenant_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[StartGenerationItemRender, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return StartGenerationItemRender(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_item(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, *, with_reference_asset: bool = True
) -> GenerationItem:
    input_asset_ids = []
    if with_reference_asset:
        asset = Asset.create(
            tenant_id,
            storage_key="tenants/x/input/a.jpg",
            sha256="a" * 64,
            mime="image/jpeg",
            width=1080,
            height=1350,
            bytes_=204_800,
            kind=AssetKind.INPUT,
            source="upload",
            now=_NOW,
        )
        await uow_factory.assets.add(asset)
        input_asset_ids = [asset.id]

    item = GenerationItem.create(
        tenant_id,
        new_generation_request_id(),
        new_catalog_image_slot_id(),
        new_catalog_template_id(),
        attempt_no=1,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={"aspect_ratio": "4:5"},
        seed=42,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=input_asset_ids,
        now=_NOW,
    )
    await uow_factory.generation_items.add(item)
    return item


async def test_returns_none_when_nothing_is_claimable() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case(tenant_id=new_tenant_id()) is None


async def test_claims_the_job_and_returns_a_render_context() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    item = await _seed_item(uow_factory, tenant_id)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"generation_item_id": str(item.id)},
        run_at=_NOW,
        now=_NOW,
    )

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is not None
    assert ctx.item_id == item.id
    assert ctx.prompt == "a scene"
    assert ctx.model == "nano-banana-2"
    assert ctx.seed == 42
    assert ctx.model_params == {"aspect_ratio": "4:5"}
    assert ctx.reference_storage_keys == ["tenants/x/input/a.jpg"]

    stored = await uow_factory.generation_items.get(tenant_id, item.id)
    assert stored is not None
    assert stored.status.value == "running"


async def test_ignores_a_due_job_of_a_different_type() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type="something.else",
        payload={"generation_item_id": str(new_generation_request_id())},
        run_at=_NOW,
        now=_NOW,
    )

    assert await use_case(tenant_id=tenant_id) is None


async def test_a_job_pointing_at_a_missing_item_is_dead_lettered_and_returns_none() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    missing_item_id = new_generation_item_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"generation_item_id": str(missing_item_id)},
        run_at=_NOW,
        now=_NOW,
        max_attempts=1,
    )

    result = await use_case(tenant_id=tenant_id)

    assert result is None
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"


async def test_a_missing_reference_asset_raises_and_leaves_the_item_pending() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    item = await _seed_item(uow_factory, tenant_id, with_reference_asset=False)
    # Point the item at a reference asset that was never registered - a data
    # inconsistency fan-out should never produce, exercised here directly.
    item.input_asset_ids.append(new_asset_id())
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"generation_item_id": str(item.id)},
        run_at=_NOW,
        now=_NOW,
    )

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=tenant_id)

    stored = await uow_factory.generation_items.get(tenant_id, item.id)
    assert stored is not None
    assert stored.status.value == "pending"
