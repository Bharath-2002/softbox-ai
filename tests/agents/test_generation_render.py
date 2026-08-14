"""Exercises the real ``StartGenerationItemRender``/
``CompleteGenerationItemRender``/``FailGenerationItemRender`` use cases wired
together the way ``bootstrap/di.py`` will wire them - only ``ObjectStorage``
and ``ImageGeneration`` are fakes. Proves the agent owns no transaction of
its own, the same property ``test_template_analysis.py`` proves for that
agent.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

from PIL import Image

from app.agents.generation_render import GenerationRenderAgent
from app.entities.asset import Asset, AssetKind
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.features.generation.complete_generation_item_render import CompleteGenerationItemRender
from app.features.generation.fail_generation_item_render import FailGenerationItemRender
from app.features.generation.start_generation_item_render import (
    JOB_TYPE,
    StartGenerationItemRender,
)
from app.services.ports.image_generation import GeneratedImage
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.image_generation import FakeImageGeneration
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(
    uow_factory: FakeUnitOfWorkFactory,
    storage: InMemoryObjectStorage,
    image_generation: FakeImageGeneration,
) -> GenerationRenderAgent:
    clock = FakeClock(_NOW)
    return GenerationRenderAgent(
        StartGenerationItemRender(uow_factory, clock),
        CompleteGenerationItemRender(uow_factory, storage, clock),
        FailGenerationItemRender(uow_factory, clock),
        storage,
        image_generation,
    )


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color="blue").save(buf, format="PNG")
    return buf.getvalue()


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, storage: InMemoryObjectStorage, tenant_id: object
) -> tuple[GenerationItem, UUID]:
    request = GenerationRequest.create(
        tenant_id,
        new_product_id(),
        new_product_variant_id(),
        new_category_spec_version_id(),
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.generation_requests.add(request)

    storage_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(storage_key, b"reference-bytes")
    reference_asset = Asset.create(
        tenant_id,
        storage_key=storage_key,
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=16,
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(reference_asset)

    item = GenerationItem.create(
        tenant_id,
        request.id,
        new_catalog_image_slot_id(),
        new_catalog_template_id(),
        attempt_no=1,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={},
        seed=1,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=[reference_asset.id],
        now=_NOW,
    )
    await uow_factory.generation_items.add(item)
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"generation_item_id": str(item.id)},
        run_at=_NOW,
        now=_NOW,
    )
    return item, job_id


async def test_returns_none_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    agent = _agent(uow_factory, storage, FakeImageGeneration())

    assert await agent.run(tenant_id=new_tenant_id()) is None


async def test_a_successful_render_calls_the_provider_with_reference_bytes() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    image_generation = FakeImageGeneration()
    image_generation.next_result = GeneratedImage(
        image_bytes=_png_bytes(), mime="image/png", cost_micros=2_000, latency_ms=500
    )
    tenant_id = new_tenant_id()
    _item, job_id = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, image_generation)

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.status.value == "succeeded"
    assert result.cost_micros == 2_000
    assert result.latency_ms == 500
    assert image_generation.calls == [("a scene", "nano-banana-2", 1, {}, 1)]

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "succeeded"


async def test_a_provider_failure_reaches_failed_not_an_unhandled_exception() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    image_generation = FakeImageGeneration()
    image_generation.next_error = RuntimeError("provider is down")
    tenant_id = new_tenant_id()
    await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, image_generation)

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.status.value == "failed"
    assert result.error_code == "RuntimeError"
    assert result.error_detail == "provider is down"


async def test_missing_reference_bytes_also_reaches_failed() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    image_generation = FakeImageGeneration()
    tenant_id = new_tenant_id()
    item, _job_id = await _seed(uow_factory, storage, tenant_id)
    reference_asset = await uow_factory.assets.get(tenant_id, item.input_asset_ids[0])
    assert reference_asset is not None
    # Delete the bytes after seeding so `ObjectStorage.read` raises inside
    # the agent's try block - a storage failure is just as retryable as a
    # provider failure and must not propagate as an unhandled exception.
    await storage.delete(reference_asset.storage_key)
    agent = _agent(uow_factory, storage, image_generation)

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.status.value == "failed"
