from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage
from app.entities.catalog_template import CatalogTemplate
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.entities.image_slots import CatalogImageSlot
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.entities.setting import Setting, SettingScope
from app.features.generation.complete_catalog_image_qc import CompleteCatalogImageQc
from app.services.ports.quality_control import QcVerdict
from app.services.spec_snapshot import build_snapshot
from app.shared.errors import NotFoundError
from app.shared.ids import (
    CatalogTemplateId,
    ProductVariantId,
    TenantId,
    new_asset_id,
    new_catalog_image_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PASS = QcVerdict(passed=True, checks={"subject_present": True}, reason=None)
_FAIL = QcVerdict(passed=False, checks={"colour_delta": False}, reason="colour mismatch")


def _use_case() -> tuple[CompleteCatalogImageQc, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CompleteCatalogImageQc(uow_factory, FakeClock(_NOW)), uow_factory


async def _job_id(uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId) -> object:
    return await uow_factory.task_queue.enqueue(
        tenant_id, job_type="x", payload={}, run_at=_NOW, now=_NOW
    )


async def _image_for_item(
    uow_factory: FakeUnitOfWorkFactory,
    tenant_id: TenantId,
    variant_id: ProductVariantId,
    item: GenerationItem,
) -> CatalogImage:
    """A `generation_item` that reached `succeeded` always has a
    `catalog_images` row - `CompleteGenerationItemRender` creates it. Tests
    below drive the ladder across several failures, each needing its own
    winning item's own image row, without re-running that whole use case."""
    output_asset = new_asset_id()
    item.mark_running()
    item.mark_succeeded(output_asset_id=output_asset, cost_micros=1, latency_ms=1)
    await uow_factory.generation_items.update(item)
    image = CatalogImage.create(
        tenant_id, variant_id, item.catalog_image_slot_id, output_asset, item.id, now=_NOW
    )
    await uow_factory.catalog_images.add(image)
    return image


async def _seed(
    uow_factory: FakeUnitOfWorkFactory,
    *,
    attempt_no: int = 1,
    template_id: CatalogTemplateId | None = None,
) -> tuple[TenantId, CatalogImage, GenerationItem, Product]:
    tenant_id = new_tenant_id()
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
    variant_id = variant.id
    slot_id = closeup.id

    default_template = CatalogTemplate.create_authored(
        tenant_id,
        slot_id,
        name="Original scene",
        prompt_template="a scene",
        created_by=user_id,
        now=_NOW,
    )
    default_template.start_analysing(now=_NOW)
    default_template.mark_analysed(
        prompt_template=default_template.prompt_template,
        analysis=None,
        analysis_model=None,
        now=_NOW,
    )
    await uow_factory.catalog_templates.add(default_template)
    resolved_template_id = template_id or default_template.id

    request = GenerationRequest.create(
        tenant_id,
        product.id,
        variant_id,
        spec_version.id,
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=user_id,
        now=_NOW,
    )
    await uow_factory.generation_requests.add(request)

    item = GenerationItem.create(
        tenant_id,
        request.id,
        slot_id,
        resolved_template_id,
        attempt_no=attempt_no,
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
    output_asset_id = new_asset_id()
    item.mark_succeeded(output_asset_id=output_asset_id, cost_micros=1, latency_ms=1)
    await uow_factory.generation_items.add(item)

    image = CatalogImage.create(tenant_id, variant_id, slot_id, output_asset_id, item.id, now=_NOW)
    await uow_factory.catalog_images.add(image)

    return tenant_id, image, item, product


async def test_a_pass_reaches_pending_approval_and_completes_the_job() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image, _item, _product = await _seed(uow_factory)
    job_id = await _job_id(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id, verdict=_PASS)

    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "pending_approval"
    assert stored.qc_result == {"subject_present": True}
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "succeeded"


async def test_a_pass_auto_approves_when_approval_is_disabled_for_the_category() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image, _item, product = await _seed(uow_factory)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=product.category_id,
            key="approval.required",
            value=False,
            now=_NOW,
        )
    )
    job_id = await _job_id(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id, verdict=_PASS)

    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "approved"
    assert stored.approved_by is None
    assert stored.qc_result == {"subject_present": True}  # QC still ran and was recorded


async def test_a_pass_stays_pending_approval_when_the_setting_is_not_the_literal_bool_false() -> (
    None
):
    use_case, uow_factory = _use_case()
    tenant_id, image, _item, product = await _seed(uow_factory)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=product.category_id,
            key="approval.required",
            value="false",  # a string, not the bool False -- must not auto-approve
            now=_NOW,
        )
    )
    job_id = await _job_id(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id, verdict=_PASS)

    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "pending_approval"


async def test_a_failure_is_unaffected_by_approval_being_disabled() -> None:
    """The gate's own wording: disabling approval must not disable QC. A
    failing verdict still runs the full retry ladder regardless of the
    setting -- approval only ever gates a *pass*."""
    use_case, uow_factory = _use_case()
    tenant_id, image, _item, product = await _seed(uow_factory, attempt_no=1)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=product.category_id,
            key="approval.required",
            value=False,
            now=_NOW,
        )
    )
    job_id = await _job_id(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id, verdict=_FAIL)

    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "qc_failed"


async def test_first_failure_creates_a_retry_with_the_same_template_and_completes_the_job() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image, item, _product = await _seed(uow_factory, attempt_no=1)
    job_id = await _job_id(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id, verdict=_FAIL)

    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "qc_failed"

    siblings = await uow_factory.generation_items.list_for_request(tenant_id, item.request_id)
    assert len(siblings) == 2
    retry = next(i for i in siblings if i.id != item.id)
    assert retry.attempt_no == 2
    assert retry.template_id == item.template_id
    assert retry.prompt_rendered == item.prompt_rendered
    assert isinstance(retry.seed, int)

    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "generation_item.render_requested"
    assert events[0].payload == {"generation_item_id": str(retry.id)}

    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "succeeded"


async def test_second_failure_with_an_alternate_template_recomposes_the_prompt() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image, item, _product = await _seed(uow_factory, attempt_no=1)
    job_id1 = await _job_id(uow_factory, tenant_id)
    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id1, verdict=_FAIL)

    alternate = CatalogTemplate.create_authored(
        tenant_id,
        item.catalog_image_slot_id,
        name="Alt scene",
        prompt_template="A different scene entirely.",
        created_by=new_user_id(),
        now=_NOW,
    )
    alternate.start_analysing(now=_NOW)
    alternate.mark_analysed(
        prompt_template=alternate.prompt_template, analysis=None, analysis_model=None, now=_NOW
    )
    await uow_factory.catalog_templates.add(alternate)

    siblings = await uow_factory.generation_items.list_for_request(tenant_id, item.request_id)
    retry1 = next(i for i in siblings if i.id != item.id)
    second_image = await _image_for_item(uow_factory, tenant_id, image.variant_id, retry1)
    job_id2 = await _job_id(uow_factory, tenant_id)

    await use_case(
        tenant_id=tenant_id, catalog_image_id=second_image.id, job_id=job_id2, verdict=_FAIL
    )

    siblings_after = await uow_factory.generation_items.list_for_request(tenant_id, item.request_id)
    assert len(siblings_after) == 3
    retry2 = next(i for i in siblings_after if i.attempt_no == 3)
    assert retry2.template_id == alternate.id
    assert retry2.prompt_rendered == "A different scene entirely."


async def test_second_failure_with_no_alternate_template_reaches_human_review() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image, item, _product = await _seed(uow_factory, attempt_no=1)
    job_id1 = await _job_id(uow_factory, tenant_id)
    await use_case(tenant_id=tenant_id, catalog_image_id=image.id, job_id=job_id1, verdict=_FAIL)

    siblings = await uow_factory.generation_items.list_for_request(tenant_id, item.request_id)
    retry1 = next(i for i in siblings if i.id != item.id)
    second_image = await _image_for_item(uow_factory, tenant_id, image.variant_id, retry1)
    job_id2 = await _job_id(uow_factory, tenant_id)

    await use_case(
        tenant_id=tenant_id, catalog_image_id=second_image.id, job_id=job_id2, verdict=_FAIL
    )

    stored = await uow_factory.catalog_images.get(tenant_id, second_image.id)
    assert stored is not None
    assert stored.status.value == "human_review"
    assert stored.rejection_reason == "colour mismatch"

    siblings_after = await uow_factory.generation_items.list_for_request(tenant_id, item.request_id)
    assert len(siblings_after) == 2  # no third attempt created


async def test_an_unknown_image_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    job_id = await _job_id(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            catalog_image_id=new_catalog_image_id(),
            job_id=job_id,
            verdict=_PASS,
        )
