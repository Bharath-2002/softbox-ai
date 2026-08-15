from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.entities.publication import Publication, PublicationStatus
from app.shared.errors import ValidationError
from app.shared.ids import new_product_variant_id, new_social_account_id, new_tenant_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _publication() -> Publication:
    return Publication.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "hello", "media_asset_ids": [], "link": None},
        now=_NOW,
    )


def test_new_publication_always_starts_scheduled() -> None:
    publication = _publication()

    assert publication.status is PublicationStatus.SCHEDULED
    assert publication.attempts == 0
    assert publication.idempotency_key


def test_no_due_at_defaults_to_now() -> None:
    publication = _publication()

    assert publication.due_at == _NOW


def test_a_future_due_at_is_kept_as_given() -> None:
    future = _NOW + timedelta(days=1)
    publication = Publication.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "hello", "media_asset_ids": [], "link": None},
        due_at=future,
        now=_NOW,
    )

    assert publication.due_at == future
    assert publication.status is PublicationStatus.SCHEDULED


def test_two_publications_never_share_an_idempotency_key() -> None:
    a, b = _publication(), _publication()

    assert a.idempotency_key != b.idempotency_key


def test_mark_dispatching_then_mark_published() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)

    publication.mark_published(external_post_id="post-1", permalink="https://x", now=_NOW)

    assert publication.status is PublicationStatus.PUBLISHED
    assert publication.external_post_id == "post-1"
    assert publication.published_at == _NOW


def test_cannot_publish_without_first_marking_dispatching() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)


def test_a_retryable_failed_attempt_moves_to_failed_and_can_retry() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)
    original_key = publication.idempotency_key

    publication.record_attempt_failure(error="timeout", terminal=False, now=_NOW)

    assert publication.status is PublicationStatus.FAILED
    assert publication.attempts == 1
    assert publication.last_error == "timeout"
    assert publication.idempotency_key == original_key  # never regenerated

    # the retry edge: failed -> dispatching again, driven by TaskQueue's own
    # backoff-rescheduled job, not by the due_at poller
    publication.mark_dispatching(now=_NOW)
    assert publication.status is PublicationStatus.DISPATCHING


def test_a_terminal_failed_attempt_moves_to_dead() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)

    publication.record_attempt_failure(error="rejected", terminal=True, now=_NOW)

    assert publication.status is PublicationStatus.DEAD
    assert publication.attempts == 1


def test_cannot_mark_dispatching_from_published() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)
    publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)

    with pytest.raises(ValidationError):
        publication.mark_dispatching(now=_NOW)


def test_cannot_record_a_failure_outside_dispatching() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.record_attempt_failure(error="x", terminal=False, now=_NOW)


def test_defer_reverts_to_scheduled_and_pushes_due_at_without_incrementing_attempts() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)
    deferred_to = _NOW + timedelta(hours=6)

    publication.defer(reason="rate limited", due_at=deferred_to, now=_NOW)

    assert publication.status is PublicationStatus.SCHEDULED
    assert publication.due_at == deferred_to
    assert publication.attempts == 0
    assert publication.last_error == "rate limited"


def test_cannot_defer_outside_dispatching() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.defer(reason="x", due_at=_NOW, now=_NOW)


def test_defer_dispatch_pushes_due_at_without_changing_status() -> None:
    publication = _publication()
    new_due = _NOW + timedelta(minutes=10)

    publication.defer_dispatch(until=new_due, now=_NOW)

    assert publication.status is PublicationStatus.SCHEDULED
    assert publication.due_at == new_due


def test_cannot_defer_dispatch_outside_scheduled() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)

    with pytest.raises(ValidationError):
        publication.defer_dispatch(until=_NOW, now=_NOW)


def test_cancel_moves_scheduled_to_cancelled() -> None:
    publication = _publication()

    publication.cancel(now=_NOW)

    assert publication.status is PublicationStatus.CANCELLED


def test_cannot_cancel_once_dispatching() -> None:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)

    with pytest.raises(ValidationError):
        publication.cancel(now=_NOW)


def _published() -> Publication:
    publication = _publication()
    publication.mark_dispatching(now=_NOW)
    publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)
    return publication


def test_mark_metrics_fetch_attempted_bumps_metrics_fetched_at() -> None:
    publication = _published()

    publication.mark_metrics_fetch_attempted(now=_NOW)

    assert publication.metrics_fetched_at == _NOW
    assert publication.metrics is None


def test_cannot_mark_metrics_fetch_attempted_outside_published() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.mark_metrics_fetch_attempted(now=_NOW)


def test_record_metrics_stores_the_result() -> None:
    publication = _published()
    publication.mark_metrics_fetch_attempted(now=_NOW)

    publication.record_metrics(metrics={"impressions": 100, "likes": 5, "clicks": 2}, now=_NOW)

    assert publication.metrics == {"impressions": 100, "likes": 5, "clicks": 2}


def test_cannot_record_metrics_outside_published() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.record_metrics(metrics={"impressions": 1, "likes": 0, "clicks": 0}, now=_NOW)
