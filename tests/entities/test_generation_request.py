from __future__ import annotations

from collections.abc import Callable

import pytest

from app.entities.generation_request import GenerationRequest, GenerationRequestStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import (
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)


def _request() -> GenerationRequest:
    return GenerationRequest.create(
        new_tenant_id(),
        new_product_id(),
        new_product_variant_id(),
        new_category_spec_version_id(),
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=new_user_id(),
        now=utcnow(),
    )


def test_create_starts_queued() -> None:
    request = _request()

    assert request.status == GenerationRequestStatus.QUEUED
    assert request.completed_at is None


def test_mark_running_from_queued() -> None:
    request = _request()

    request.mark_running(now=utcnow())

    assert request.status == GenerationRequestStatus.RUNNING


@pytest.mark.parametrize(
    "mark",
    [
        lambda r, now: r.mark_succeeded(now=now),
        lambda r, now: r.mark_partially_failed(now=now),
        lambda r, now: r.mark_failed(now=now),
    ],
)
def test_terminal_transitions_from_running_set_completed_at(
    mark: Callable[[GenerationRequest, object], None],
) -> None:
    request = _request()
    request.mark_running(now=utcnow())
    now = utcnow()

    mark(request, now)

    assert request.status in {
        GenerationRequestStatus.SUCCEEDED,
        GenerationRequestStatus.PARTIALLY_FAILED,
        GenerationRequestStatus.FAILED,
    }
    assert request.completed_at == now


@pytest.mark.parametrize(
    "mark",
    [
        lambda r: r.mark_succeeded(now=utcnow()),
        lambda r: r.mark_partially_failed(now=utcnow()),
        lambda r: r.mark_failed(now=utcnow()),
    ],
)
def test_terminal_transitions_reject_a_still_queued_request(
    mark: Callable[[GenerationRequest], None],
) -> None:
    request = _request()

    with pytest.raises(ValidationError):
        mark(request)


def test_a_settled_request_cannot_be_settled_again() -> None:
    request = _request()
    request.mark_running(now=utcnow())
    request.mark_succeeded(now=utcnow())

    with pytest.raises(ValidationError):
        request.mark_failed(now=utcnow())


def test_mark_running_from_a_non_queued_status_is_rejected() -> None:
    request = _request()
    request.mark_running(now=utcnow())

    with pytest.raises(ValidationError):
        request.mark_running(now=utcnow())
