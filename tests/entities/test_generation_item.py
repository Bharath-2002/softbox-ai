from __future__ import annotations

from collections.abc import Callable

import pytest

from app.entities.generation_item import GenerationItem, GenerationItemStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_generation_request_id,
    new_tenant_id,
)


def _item() -> GenerationItem:
    return GenerationItem.create(
        new_tenant_id(),
        new_generation_request_id(),
        new_catalog_image_slot_id(),
        new_catalog_template_id(),
        attempt_no=1,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={},
        seed=42,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=[],
        now=utcnow(),
    )


def test_a_new_item_starts_pending_with_no_output() -> None:
    item = _item()

    assert item.status == GenerationItemStatus.PENDING
    assert item.output_asset_id is None
    assert item.cost_micros is None
    assert item.latency_ms is None
    assert item.error_code is None
    assert item.error_detail is None


def test_pending_can_start_running() -> None:
    item = _item()
    item.mark_running()
    assert item.status == GenerationItemStatus.RUNNING


def test_running_can_succeed_and_records_output() -> None:
    item = _item()
    item.mark_running()
    asset_id = new_asset_id()

    item.mark_succeeded(output_asset_id=asset_id, cost_micros=1_000, latency_ms=250)

    assert item.status == GenerationItemStatus.SUCCEEDED
    assert item.output_asset_id == asset_id
    assert item.cost_micros == 1_000
    assert item.latency_ms == 250


def test_running_can_fail_and_records_the_error() -> None:
    item = _item()
    item.mark_running()

    item.mark_failed(error_code="ProviderTimeout", error_detail="timed out after 30s")

    assert item.status == GenerationItemStatus.FAILED
    assert item.error_code == "ProviderTimeout"
    assert item.error_detail == "timed out after 30s"


def test_a_failed_item_can_retry_in_place_back_to_running() -> None:
    """The diagram's `item_failed -> item_running: backoff + jitter`
    self-loop — a transient-failure retry revises the same row, it does not
    spawn a new one."""
    item = _item()
    item.mark_running()
    item.mark_failed(error_code="ProviderTimeout", error_detail="boom")

    item.mark_running()

    assert item.status == GenerationItemStatus.RUNNING


def test_a_failed_item_can_deadletter() -> None:
    item = _item()
    item.mark_running()
    item.mark_failed(error_code="ProviderTimeout", error_detail="boom")

    item.mark_dead()

    assert item.status == GenerationItemStatus.DEAD


@pytest.mark.parametrize(
    "transition",
    [
        lambda item: item.mark_succeeded(
            output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1
        ),
        lambda item: item.mark_failed(error_code="x", error_detail="x"),
        lambda item: item.mark_dead(),
    ],
)
def test_pending_cannot_succeed_fail_or_deadletter_directly(
    transition: Callable[[GenerationItem], None],
) -> None:
    item = _item()

    with pytest.raises(ValidationError):
        transition(item)


def test_a_dead_item_cannot_run_again() -> None:
    item = _item()
    item.mark_running()
    item.mark_failed(error_code="x", error_detail="x")
    item.mark_dead()

    with pytest.raises(ValidationError):
        item.mark_running()


def test_a_succeeded_item_cannot_fail() -> None:
    item = _item()
    item.mark_running()
    item.mark_succeeded(output_asset_id=new_asset_id(), cost_micros=1, latency_ms=1)

    with pytest.raises(ValidationError):
        item.mark_failed(error_code="x", error_detail="x")
