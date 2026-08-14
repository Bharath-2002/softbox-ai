from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.catalog_template import CatalogTemplate
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_request import GenerationRequest
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.product import Product
from app.entities.product_input_image import ProductInputImage
from app.entities.product_variant import ProductVariant
from app.features.products.fan_out_generation_items import FanOutGenerationItems
from app.services.spec_snapshot import build_snapshot
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    GenerationRequestId,
    TenantId,
    new_asset_id,
    new_category_id,
    new_generation_request_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[FanOutGenerationItems, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = FanOutGenerationItems(
        uow_factory, FakeClock(_NOW), provider="nano-banana", model="nano-banana-2"
    )
    return use_case, uow_factory


async def _seed(
    uow_factory: FakeUnitOfWorkFactory,
    *,
    with_default_template: bool = True,
    with_required_input: bool = True,
) -> tuple[TenantId, GenerationRequest]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()

    garment_body = InputImageSlot.create(
        tenant_id,
        category_id,
        key="garment_body",
        label="Garment body",
        description="Front-facing",
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
    requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, garment_body.id, role="garment_body", prompt_position=0, now=_NOW
    )
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[garment_body],
        catalog_image_slots=[closeup],
        catalog_slot_input_requirements={closeup.id: [requirement]},
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

    if with_default_template:
        template = CatalogTemplate.create_authored(
            tenant_id,
            closeup.id,
            name="Marble tabletop",
            prompt_template="A flat-lay, {{input.garment_body}} shown.",
            created_by=user_id,
            now=_NOW,
            is_default=True,
        )
        template.start_analysing(now=_NOW)
        template.mark_analysed(
            prompt_template=template.prompt_template, analysis=None, analysis_model=None, now=_NOW
        )
        await uow_factory.catalog_templates.add(template)

    if with_required_input:
        image = ProductInputImage.create(
            tenant_id,
            product.id,
            input_image_slot_id=garment_body.id,
            asset_id=new_asset_id(),
            created_by=user_id,
            now=_NOW,
        )
        await uow_factory.product_input_images.add(image)

    return tenant_id, request


async def test_fans_out_one_item_per_required_slot_and_marks_the_request_running() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request = await _seed(uow_factory)

    items = await use_case(tenant_id=tenant_id, generation_request_id=request.id)

    assert len(items) == 1
    item = items[0]
    assert item.status.value == "pending"
    assert item.provider == "nano-banana"
    assert item.model == "nano-banana-2"
    assert item.prompt_rendered.startswith("A flat-lay, {{input.garment_body}} shown.")
    assert len(item.input_asset_ids) == 1

    stored_request = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored_request is not None
    assert stored_request.status.value == "running"

    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "generation_item.render_requested"
    assert events[0].payload == {"generation_item_id": str(item.id)}


async def test_fanning_out_twice_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request = await _seed(uow_factory)
    await use_case(tenant_id=tenant_id, generation_request_id=request.id)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, generation_request_id=request.id)


async def test_a_slot_with_no_default_analysed_template_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request = await _seed(uow_factory, with_default_template=False)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, generation_request_id=request.id)

    stored_request = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored_request is not None
    assert stored_request.status.value == "queued"  # nothing written on failure
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert events == []


async def test_a_missing_required_input_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request = await _seed(uow_factory, with_required_input=False)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, generation_request_id=request.id)


async def test_unknown_request_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            generation_request_id=GenerationRequestId(new_generation_request_id()),
        )
