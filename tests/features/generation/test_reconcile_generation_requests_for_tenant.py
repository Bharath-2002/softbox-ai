from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.entities.image_slots import CatalogImageSlot
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.features.generation.reconcile_generation_requests_for_tenant import (
    ReconcileGenerationRequestsForTenant,
)
from app.services.spec_snapshot import build_snapshot
from app.shared.errors import NotFoundError
from app.shared.ids import (
    TenantId,
    new_asset_id,
    new_catalog_template_id,
    new_category_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_QUOTA_METRIC = "generation.images"


def _use_case() -> tuple[ReconcileGenerationRequestsForTenant, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ReconcileGenerationRequestsForTenant(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_running_request(
    uow_factory: FakeUnitOfWorkFactory,
    *,
    tenant_id: TenantId | None = None,
    slot_count: int = 1,
    reserve_quota: bool = True,
) -> tuple[TenantId, GenerationRequest, list[object]]:
    tenant_id = tenant_id if tenant_id is not None else new_tenant_id()
    category_id = new_category_id()
    user_id = new_user_id()

    slots = [
        CatalogImageSlot.create(
            tenant_id,
            category_id,
            key=f"slot_{i}",
            label=f"Slot {i}",
            aspect_ratio="4:5",
            target_width=1080,
            target_height=1350,
            now=_NOW,
        )
        for i in range(slot_count)
    ]
    snapshot = build_snapshot(
        attribute_definitions=[],
        variant_axes=[],
        variant_axis_values={},
        input_image_slots=[],
        catalog_image_slots=slots,
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

    quota_reservation_id = None
    if reserve_quota:
        period = _NOW.strftime("%Y-%m")
        await uow_factory.quota_reservations.ensure_period(
            tenant_id, period=period, metric=_QUOTA_METRIC, limit_value=100, now=_NOW
        )
        await uow_factory.quota_reservations.reserve(
            tenant_id, period=period, metric=_QUOTA_METRIC, quantity=slot_count, now=_NOW
        )
        reservation = await uow_factory.quota_reservations.get(
            tenant_id, period=period, metric=_QUOTA_METRIC
        )
        assert reservation is not None
        quota_reservation_id = reservation.id

    request = GenerationRequest.create(
        tenant_id,
        product.id,
        variant.id,
        spec_version.id,
        settings_snapshot={},
        quota_reservation_id=quota_reservation_id,
        requested_by=user_id,
        now=_NOW,
    )
    request.mark_running(now=_NOW)
    await uow_factory.generation_requests.add(request)

    return tenant_id, request, slots


async def _add_item(
    uow_factory: FakeUnitOfWorkFactory,
    tenant_id: TenantId,
    request: GenerationRequest,
    slot: object,
    *,
    outcome: str,
) -> GenerationItem:
    item = GenerationItem.create(
        tenant_id,
        request.id,
        slot.id,  # type: ignore[attr-defined]
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
    if outcome == "succeeded":
        item.mark_running()
        item.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)
    elif outcome == "dead":
        item.mark_running()
        item.mark_failed(error_code="e", error_detail="d")
        item.mark_dead()
    elif outcome != "pending":
        raise ValueError(f"Unknown outcome {outcome!r}.")
    await uow_factory.generation_items.add(item)
    return item


async def test_reconciling_with_nothing_running_settles_zero() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case(new_tenant_id()) == 0


async def test_all_slots_succeeded_settles_and_commits_quota() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")

    settled = await use_case(tenant_id)

    assert settled == 1
    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None
    assert stored.status.value == "succeeded"
    assert stored.completed_at == _NOW
    period = _NOW.strftime("%Y-%m")
    reservation = await uow_factory.quota_reservations.get(
        tenant_id, period=period, metric=_QUOTA_METRIC
    )
    assert reservation is not None
    assert reservation.committed == 1
    assert reservation.reserved == 1


async def test_all_slots_dead_settles_failed_and_releases_quota() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="dead")

    settled = await use_case(tenant_id)

    assert settled == 1
    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None
    assert stored.status.value == "failed"
    period = _NOW.strftime("%Y-%m")
    reservation = await uow_factory.quota_reservations.get(
        tenant_id, period=period, metric=_QUOTA_METRIC
    )
    assert reservation is not None
    assert reservation.committed == 0
    assert reservation.reserved == 0


async def test_a_mixed_outcome_settles_partially_failed_and_splits_quota() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory, slot_count=2)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")
    await _add_item(uow_factory, tenant_id, request, slots[1], outcome="dead")

    settled = await use_case(tenant_id)

    assert settled == 1
    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None
    assert stored.status.value == "partially_failed"
    period = _NOW.strftime("%Y-%m")
    reservation = await uow_factory.quota_reservations.get(
        tenant_id, period=period, metric=_QUOTA_METRIC
    )
    assert reservation is not None
    assert reservation.committed == 1
    assert reservation.reserved == 1  # 2 reserved, 1 released for the dead slot


async def test_a_request_with_a_pending_slot_is_left_running() -> None:
    use_case, uow_factory = _use_case()
    # A slot with zero items counts as failed, not pending (see
    # `compute_rollup`'s docstring) -- use two slots and leave one with an
    # item still `pending` to actually exercise "still in flight" here.
    tenant_id, request, slots = await _seed_running_request(uow_factory, slot_count=2)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")
    await _add_item(uow_factory, tenant_id, request, slots[1], outcome="pending")

    settled = await use_case(tenant_id)

    assert settled == 0
    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None
    assert stored.status.value == "running"


async def test_a_request_with_no_quota_reservation_settles_without_touching_quota() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory, reserve_quota=False)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")

    settled = await use_case(tenant_id)

    assert settled == 1
    stored = await uow_factory.generation_requests.get(tenant_id, request.id)
    assert stored is not None
    assert stored.status.value == "succeeded"
    period = _NOW.strftime("%Y-%m")
    assert (
        await uow_factory.quota_reservations.get(tenant_id, period=period, metric=_QUOTA_METRIC)
        is None
    )


async def test_reconciling_respects_the_limit() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    for _ in range(3):
        _tenant_id, request, slots = await _seed_running_request(uow_factory, tenant_id=tenant_id)
        await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")

    settled = await use_case(tenant_id, limit=2)

    assert settled == 2


async def test_a_settled_request_is_not_processed_again() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")

    first = await use_case(tenant_id)
    second = await use_case(tenant_id)

    assert first == 1
    assert second == 0
    period = _NOW.strftime("%Y-%m")
    reservation = await uow_factory.quota_reservations.get(
        tenant_id, period=period, metric=_QUOTA_METRIC
    )
    assert reservation is not None
    assert reservation.committed == 1  # unchanged by the second, no-op call


async def test_a_mismatched_quota_reservation_id_raises_instead_of_silently_skipping() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, request, slots = await _seed_running_request(uow_factory)
    await _add_item(uow_factory, tenant_id, request, slots[0], outcome="succeeded")
    # Simulate the reservation row having been deleted or re-keyed out from
    # under the request between reservation and settlement.
    request.quota_reservation_id = uuid.uuid4()
    await uow_factory.generation_requests.update(request)

    with pytest.raises(NotFoundError):
        await use_case(tenant_id)
