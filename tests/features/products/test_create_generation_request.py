from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_request import GenerationRequestStatus
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.features.products.create_generation_request import CreateGenerationRequest
from app.shared.errors import NotFoundError, QuotaExceededError
from app.shared.ids import (
    CategorySpecVersionId,
    new_catalog_image_slot_id,
    new_category_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_METRIC = "generation.images"


def _use_case() -> tuple[CreateGenerationRequest, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreateGenerationRequest(uow_factory, FakeClock(_NOW)), uow_factory


def _slot(*, required: bool) -> dict[str, object]:
    return {
        "id": str(new_catalog_image_slot_id()),
        "category_id": "x",
        "key": "closeup",
        "label": "Closeup",
        "description": None,
        "position": 0,
        "aspect_ratio": "4:5",
        "target_width": 1080,
        "target_height": 1350,
        "is_required": required,
        "input_requirements": [],
    }


async def _seed_product_and_variant(
    uow_factory: FakeUnitOfWorkFactory,
    tenant_id: object,
    *,
    required_slots: int,
    optional_slots: int = 0,
) -> tuple[Product, ProductVariant, CategorySpecVersionId]:
    category_id = new_category_id()
    user_id = new_user_id()
    slots = [_slot(required=True) for _ in range(required_slots)] + [
        _slot(required=False) for _ in range(optional_slots)
    ]
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=1,
        snapshot={
            "attribute_definitions": [],
            "variant_axes": [],
            "input_image_slots": [],
            "catalog_image_slots": slots,
        },
        published_by=user_id,
        now=_NOW,
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
    return product, variant, spec_version.id


async def test_reserves_quota_for_exactly_the_required_slot_count_and_creates_the_request() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product, variant, spec_version_id = await _seed_product_and_variant(
        uow_factory, tenant_id, required_slots=3, optional_slots=2
    )
    period = _NOW.strftime("%Y-%m")
    await uow_factory.quota_reservations.ensure_period(
        tenant_id, period=period, metric=_METRIC, limit_value=10, now=_NOW
    )

    request = await use_case(
        tenant_id=tenant_id,
        product_id=product.id,
        variant_id=variant.id,
        requested_by=new_user_id(),
    )

    assert request.status == GenerationRequestStatus.QUEUED
    assert request.product_id == product.id
    assert request.variant_id == variant.id
    assert request.spec_version_id == spec_version_id

    reservation = await uow_factory.quota_reservations.get(tenant_id, period=period, metric=_METRIC)
    assert reservation is not None
    assert reservation.reserved == 3  # only the required slots, not the optional ones
    assert request.quota_reservation_id == reservation.id

    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None

    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "generation_request.created"
    assert events[0].payload == {"generation_request_id": str(request.id)}


async def test_over_quota_raises_and_writes_nothing() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product, variant, _ = await _seed_product_and_variant(uow_factory, tenant_id, required_slots=3)
    period = _NOW.strftime("%Y-%m")
    await uow_factory.quota_reservations.ensure_period(
        tenant_id, period=period, metric=_METRIC, limit_value=2, now=_NOW
    )

    with pytest.raises(QuotaExceededError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            variant_id=variant.id,
            requested_by=new_user_id(),
        )

    reservation = await uow_factory.quota_reservations.get(tenant_id, period=period, metric=_METRIC)
    assert reservation is not None
    assert reservation.reserved == 0
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert events == []


async def test_unprovisioned_quota_fails_closed() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product, variant, _ = await _seed_product_and_variant(uow_factory, tenant_id, required_slots=1)

    with pytest.raises(QuotaExceededError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            variant_id=variant.id,
            requested_by=new_user_id(),
        )


async def test_a_spec_with_no_required_slots_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product, variant, _ = await _seed_product_and_variant(
        uow_factory, tenant_id, required_slots=0, optional_slots=2
    )

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            variant_id=variant.id,
            requested_by=new_user_id(),
        )


async def test_unknown_product_is_not_found() -> None:
    use_case, _uow_factory = _use_case()
    tenant_id = new_tenant_id()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=new_product_id(),
            variant_id=new_product_variant_id(),
            requested_by=new_user_id(),
        )


async def test_variant_belonging_to_a_different_product_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    product, _, _ = await _seed_product_and_variant(uow_factory, tenant_id, required_slots=1)
    _, other_variant, _ = await _seed_product_and_variant(uow_factory, tenant_id, required_slots=1)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            product_id=product.id,
            variant_id=other_variant.id,
            requested_by=new_user_id(),
        )
