from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

import pytest
from PIL import Image
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.features.generation.complete_generation_item_render import CompleteGenerationItemRender
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _png_bytes(*, color: str = "green") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color=color).save(buf, format="PNG")
    return buf.getvalue()


def _use_case() -> tuple[
    CompleteGenerationItemRender, InMemoryObjectStorage, FakeUnitOfWorkFactory
]:
    storage = InMemoryObjectStorage()
    uow_factory = FakeUnitOfWorkFactory()
    return CompleteGenerationItemRender(uow_factory, storage, FakeClock(_NOW)), storage, uow_factory


async def _job_id(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> UUID:
    return await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW
    )


async def _seed(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, GenerationItem]:
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    slot_id = new_catalog_image_slot_id()

    request = GenerationRequest.create(
        tenant_id,
        new_product_id(),
        variant_id,
        new_category_spec_version_id(),
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.generation_requests.add(request)

    item = GenerationItem.create(
        tenant_id,
        request.id,
        slot_id,
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

    return tenant_id, item


async def test_registers_a_generated_asset_and_a_pending_qc_catalog_image() -> None:
    use_case, _storage, uow_factory = _use_case()
    tenant_id, item = await _seed(uow_factory)

    result = await use_case(
        tenant_id=tenant_id,
        item_id=item.id,
        job_id=await _job_id(uow_factory, tenant_id),
        image_bytes=_png_bytes(),
        cost_micros=1_000,
        latency_ms=250,
    )

    assert result.status.value == "succeeded"
    assert result.output_asset_id is not None
    assert result.cost_micros == 1_000
    assert result.latency_ms == 250

    asset = await uow_factory.assets.get(tenant_id, result.output_asset_id)
    assert asset is not None
    assert asset.kind.value == "generated"
    assert asset.mime == "image/png"

    request = await uow_factory.generation_requests.get(tenant_id, item.request_id)
    assert request is not None
    images = await uow_factory.catalog_images.list_for_variant(tenant_id, request.variant_id)
    assert len(images) == 1
    assert images[0].status.value == "pending_qc"
    assert images[0].asset_id == result.output_asset_id
    assert images[0].generation_item_id == item.id
    assert images[0].superseded_by is None


async def test_supersedes_an_existing_live_catalog_image() -> None:
    use_case, _storage, uow_factory = _use_case()
    tenant_id, item = await _seed(uow_factory)
    request = await uow_factory.generation_requests.get(tenant_id, item.request_id)
    assert request is not None

    existing = CatalogImage.create(
        tenant_id,
        request.variant_id,
        item.catalog_image_slot_id,
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    await uow_factory.catalog_images.add(existing)

    await use_case(
        tenant_id=tenant_id,
        item_id=item.id,
        job_id=await _job_id(uow_factory, tenant_id),
        image_bytes=_png_bytes(),
        cost_micros=1_000,
        latency_ms=250,
    )

    images = await uow_factory.catalog_images.list_for_variant(tenant_id, request.variant_id)
    assert len(images) == 2
    superseded = next(i for i in images if i.id == existing.id)
    live = next(i for i in images if i.id != existing.id)
    assert superseded.superseded_by == live.id
    assert live.superseded_by is None


async def test_an_unknown_item_is_not_found() -> None:
    use_case, _storage, uow_factory = _use_case()
    tenant_id = new_tenant_id()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            item_id=new_generation_item_id(),
            job_id=await _job_id(uow_factory, tenant_id),
            image_bytes=_png_bytes(),
            cost_micros=1,
            latency_ms=1,
        )
