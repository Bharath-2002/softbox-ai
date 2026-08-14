from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage
from app.entities.product_variant import ProductVariant
from app.features.content.generate_content_draft import GenerateContentDraft
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_generation_item_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_MODEL = "fake-text-model"


def _use_case() -> tuple[GenerateContentDraft, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return GenerateContentDraft(uow_factory, FakeClock(_NOW), model=_MODEL), uow_factory


async def _seed_variant_with_approved_image(
    uow_factory: FakeUnitOfWorkFactory,
) -> tuple[object, object]:
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    image = CatalogImage.create(
        tenant_id,
        variant.id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    image.mark_qc_passed(qc_result={}, now=_NOW)
    image.approve(approved_by=new_user_id(), now=_NOW)
    await uow_factory.catalog_images.add(image)
    return tenant_id, variant.id


async def test_enqueues_a_content_draft_generate_requested_event() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id = await _seed_variant_with_approved_image(uow_factory)

    await use_case(tenant_id=tenant_id, variant_id=variant_id, channel="instagram", locale="en")

    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "content_draft.generate_requested"
    assert events[0].payload == {
        "variant_id": str(variant_id),
        "channel": "instagram",
        "locale": "en",
        "model": _MODEL,
    }


async def test_an_unknown_variant_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            variant_id=new_product_variant_id(),
            channel="instagram",
            locale="en",
        )


async def test_a_variant_with_no_approved_images_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, variant_id=variant.id, channel="instagram", locale="en")


async def test_a_pending_approval_image_does_not_count_as_approved() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    image = CatalogImage.create(
        tenant_id,
        variant.id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    image.mark_qc_passed(qc_result={}, now=_NOW)
    await uow_factory.catalog_images.add(image)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, variant_id=variant.id, channel="instagram", locale="en")
