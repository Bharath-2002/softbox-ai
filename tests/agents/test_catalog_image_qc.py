"""Exercises the real ``StartCatalogImageQc``/``CompleteCatalogImageQc``/
``FailCatalogImageQc`` use cases wired together the way ``bootstrap/di.py``
will wire them - only ``ObjectStorage`` and ``QualityControl`` are fakes.
Proves the agent owns no transaction of its own, the same property
``test_generation_render.py``/``test_template_analysis.py`` prove for their
own agents.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.catalog_image_qc import CatalogImageQcAgent
from app.entities.asset import Asset, AssetKind
from app.entities.catalog_image import CatalogImage
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.entities.image_slots import CatalogImageSlot
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.features.generation.complete_catalog_image_qc import CompleteCatalogImageQc
from app.features.generation.fail_catalog_image_qc import FailCatalogImageQc
from app.features.generation.start_catalog_image_qc import JOB_TYPE, StartCatalogImageQc
from app.services.ports.quality_control import QcVerdict
from app.services.spec_snapshot import build_snapshot
from app.shared.ids import new_catalog_template_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.quality_control import FakeQualityControl
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(
    uow_factory: FakeUnitOfWorkFactory,
    storage: InMemoryObjectStorage,
    quality_control: FakeQualityControl,
) -> CatalogImageQcAgent:
    clock = FakeClock(_NOW)
    return CatalogImageQcAgent(
        StartCatalogImageQc(uow_factory, clock),
        CompleteCatalogImageQc(uow_factory, clock),
        FailCatalogImageQc(uow_factory, clock),
        storage,
        quality_control,
    )


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, storage: InMemoryObjectStorage, tenant_id: object
) -> CatalogImage:
    user_id = new_user_id()
    category = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    category_id = category.id

    closeup = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=[closeup],
        catalog_slot_input_requirements={},
    )
    spec_version = CategorySpecVersion.create(
        tenant_id, category_id, version=1, snapshot=snapshot, published_by=user_id, now=_NOW
    )
    await uow_factory.category_spec_versions.add(spec_version)

    product = Product.create(
        tenant_id, category_id, spec_version.id, attributes={}, created_by=user_id, now=_NOW
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=user_id, now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    request = GenerationRequest.create(
        tenant_id,
        product.id,
        variant.id,
        spec_version.id,
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=user_id,
        now=_NOW,
    )
    await uow_factory.generation_requests.add(request)

    ref_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(ref_key, b"reference-bytes")
    reference_asset = Asset.create(
        tenant_id,
        storage_key=ref_key,
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

    out_key = storage.new_storage_key(tenant_id, kind="generated", extension="png")
    await storage.write(out_key, b"generated-bytes")
    output_asset = Asset.create(
        tenant_id,
        storage_key=out_key,
        sha256="b" * 64,
        mime="image/png",
        width=1080,
        height=1350,
        bytes_=16,
        kind=AssetKind.GENERATED,
        source="generation",
        now=_NOW,
    )
    await uow_factory.assets.add(output_asset)

    item = GenerationItem.create(
        tenant_id,
        request.id,
        closeup.id,
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
    item.mark_running()
    item.mark_succeeded(output_asset_id=output_asset.id, cost_micros=1, latency_ms=1)
    await uow_factory.generation_items.add(item)

    image = CatalogImage.create(
        tenant_id,
        request.variant_id,
        item.catalog_image_slot_id,
        output_asset.id,
        item.id,
        now=_NOW,
    )
    await uow_factory.catalog_images.add(image)

    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"catalog_image_id": str(image.id)},
        run_at=_NOW,
        now=_NOW,
    )
    return image


async def test_returns_false_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    agent = _agent(uow_factory, storage, FakeQualityControl())

    assert await agent.run(tenant_id=new_tenant_id()) is False


async def test_a_passing_verdict_reaches_pending_approval() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    quality_control = FakeQualityControl()
    tenant_id = new_tenant_id()
    image = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, quality_control)

    ran = await agent.run(tenant_id=tenant_id)

    assert ran is True
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "pending_approval"
    assert quality_control.calls == [(b"generated-bytes", 1, None)]


async def test_a_failing_verdict_creates_a_retry() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    quality_control = FakeQualityControl()
    quality_control.next_result = QcVerdict(
        passed=False, checks={"colour_delta": False}, reason="colour mismatch"
    )
    tenant_id = new_tenant_id()
    image = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, quality_control)

    ran = await agent.run(tenant_id=tenant_id)

    assert ran is True
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "qc_failed"
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "generation_item.render_requested"


async def test_a_provider_failure_reschedules_the_job_not_an_unhandled_exception() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    quality_control = FakeQualityControl()
    quality_control.next_error = RuntimeError("provider is down")
    tenant_id = new_tenant_id()
    image = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, quality_control)

    ran = await agent.run(tenant_id=tenant_id)

    assert ran is True
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "pending_qc"  # untouched
