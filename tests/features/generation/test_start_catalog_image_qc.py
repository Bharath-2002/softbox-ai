from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.asset import Asset, AssetKind
from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.entities.catalog_image import CatalogImage
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_item import GenerationItem
from app.entities.image_slots import CatalogImageSlot
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.features.generation.start_catalog_image_qc import JOB_TYPE, StartCatalogImageQc
from app.services.spec_snapshot import build_snapshot
from app.shared.ids import (
    new_catalog_image_id,
    new_catalog_template_id,
    new_category_id,
    new_generation_request_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[StartCatalogImageQc, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return StartCatalogImageQc(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, CatalogImage]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()

    colour_attr = AttributeDefinition.create(
        tenant_id,
        category_id,
        key="colour",
        label="Colour",
        data_type=AttributeDataType.TEXT,
        semantic_role=SemanticRole.COLOUR,
        now=_NOW,
    )
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
        attribute_definitions=[colour_attr],
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
        tenant_id,
        category_id,
        spec_version.id,
        attributes={"colour": "maroon"},
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=user_id, now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    reference_asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/input/ref.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=1000,
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(reference_asset)

    output_asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/generated/out.png",
        sha256="b" * 64,
        mime="image/png",
        width=1080,
        height=1350,
        bytes_=2000,
        kind=AssetKind.GENERATED,
        source="generation",
        now=_NOW,
    )
    await uow_factory.assets.add(output_asset)

    item = GenerationItem.create(
        tenant_id,
        new_generation_request_id(),
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
    item.mark_succeeded(output_asset_id=output_asset.id, cost_micros=1_000, latency_ms=250)
    await uow_factory.generation_items.add(item)

    image = CatalogImage.create(
        tenant_id, variant.id, closeup.id, output_asset.id, item.id, now=_NOW
    )
    await uow_factory.catalog_images.add(image)

    return tenant_id, image


async def test_returns_none_when_nothing_is_claimable() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case(tenant_id=new_tenant_id()) is None


async def test_claims_the_job_and_returns_a_qc_context() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image = await _seed(uow_factory)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"catalog_image_id": str(image.id)},
        run_at=_NOW,
        now=_NOW,
    )

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is not None
    assert ctx.catalog_image_id == image.id
    assert ctx.image_storage_key == "tenants/x/generated/out.png"
    assert ctx.reference_storage_keys == ["tenants/x/input/ref.jpg"]
    assert ctx.slot_spec["key"] == "closeup"
    assert ctx.declared_colour == "maroon"


async def test_ignores_a_due_job_of_a_different_type() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    await uow_factory.task_queue.enqueue(
        tenant_id, job_type="something.else", payload={}, run_at=_NOW, now=_NOW
    )

    assert await use_case(tenant_id=tenant_id) is None


async def test_a_job_pointing_at_a_missing_image_is_dead_lettered_and_returns_none() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    missing_image_id = new_catalog_image_id()
    job_id = await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"catalog_image_id": str(missing_image_id)},
        run_at=_NOW,
        now=_NOW,
        max_attempts=1,
    )

    result = await use_case(tenant_id=tenant_id)

    assert result is None
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "dead"
