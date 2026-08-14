from __future__ import annotations

from datetime import UTC, datetime

from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequestStatus
from app.services.generation_request_rollup import compute_rollup
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_generation_request_id,
    new_tenant_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _item(*, slot_id: object, attempt_no: int = 1) -> GenerationItem:
    return GenerationItem.create(
        new_tenant_id(),
        new_generation_request_id(),
        slot_id,  # type: ignore[arg-type]
        new_catalog_template_id(),
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


def test_all_slots_succeeded_reaches_succeeded() -> None:
    slot_a, slot_b = new_catalog_image_slot_id(), new_catalog_image_slot_id()
    item_a, item_b = _item(slot_id=slot_a), _item(slot_id=slot_b)
    item_a.mark_running()
    item_a.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)
    item_b.mark_running()
    item_b.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)

    rollup = compute_rollup([str(slot_a), str(slot_b)], [item_a, item_b])

    assert rollup.status == GenerationRequestStatus.SUCCEEDED
    assert rollup.succeeded_slot_count == 2
    assert rollup.failed_slot_count == 0


def test_all_slots_dead_reaches_failed() -> None:
    slot_a, slot_b = new_catalog_image_slot_id(), new_catalog_image_slot_id()
    item_a, item_b = _item(slot_id=slot_a), _item(slot_id=slot_b)
    item_a.mark_running()
    item_a.mark_failed(error_code="e", error_detail="d")
    item_a.mark_dead()
    item_b.mark_running()
    item_b.mark_failed(error_code="e", error_detail="d")
    item_b.mark_dead()

    rollup = compute_rollup([str(slot_a), str(slot_b)], [item_a, item_b])

    assert rollup.status == GenerationRequestStatus.FAILED
    assert rollup.succeeded_slot_count == 0
    assert rollup.failed_slot_count == 2


def test_a_mix_of_succeeded_and_dead_slots_reaches_partially_failed() -> None:
    slot_a, slot_b = new_catalog_image_slot_id(), new_catalog_image_slot_id()
    item_a, item_b = _item(slot_id=slot_a), _item(slot_id=slot_b)
    item_a.mark_running()
    item_a.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)
    item_b.mark_running()
    item_b.mark_failed(error_code="e", error_detail="d")
    item_b.mark_dead()

    rollup = compute_rollup([str(slot_a), str(slot_b)], [item_a, item_b])

    assert rollup.status == GenerationRequestStatus.PARTIALLY_FAILED
    assert rollup.succeeded_slot_count == 1
    assert rollup.failed_slot_count == 1


def test_a_slot_still_pending_means_not_ready_to_settle() -> None:
    slot_a, slot_b = new_catalog_image_slot_id(), new_catalog_image_slot_id()
    item_a, item_b = _item(slot_id=slot_a), _item(slot_id=slot_b)
    item_a.mark_running()
    item_a.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)
    # item_b left `pending`

    rollup = compute_rollup([str(slot_a), str(slot_b)], [item_a, item_b])

    assert rollup.status is None


def test_a_slot_with_a_dead_first_attempt_and_a_succeeded_retry_counts_as_succeeded() -> None:
    slot_id = new_catalog_image_slot_id()
    first = _item(slot_id=slot_id, attempt_no=1)
    first.mark_running()
    first.mark_failed(error_code="e", error_detail="d")
    first.mark_dead()
    retry = _item(slot_id=slot_id, attempt_no=2)
    retry.mark_running()
    retry.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)

    rollup = compute_rollup([str(slot_id)], [first, retry])

    assert rollup.status == GenerationRequestStatus.SUCCEEDED
    assert rollup.succeeded_slot_count == 1


def test_a_required_slot_with_no_items_at_all_counts_as_failed() -> None:
    slot_a, slot_b = new_catalog_image_slot_id(), new_catalog_image_slot_id()
    item_a = _item(slot_id=slot_a)
    item_a.mark_running()
    item_a.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)

    rollup = compute_rollup([str(slot_a), str(slot_b)], [item_a])

    assert rollup.status == GenerationRequestStatus.PARTIALLY_FAILED
    assert rollup.failed_slot_count == 1


def test_no_required_slots_never_settles() -> None:
    assert compute_rollup([], []).status is None


def test_a_slot_with_only_a_transient_failed_item_is_not_ready_to_settle() -> None:
    slot_id = new_catalog_image_slot_id()
    item = _item(slot_id=slot_id)
    item.mark_running()
    item.mark_failed(error_code="e", error_detail="d")  # retryable in place, not dead yet

    rollup = compute_rollup([str(slot_id)], [item])

    assert rollup.status is None
