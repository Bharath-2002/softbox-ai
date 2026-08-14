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


def test_new_publication_starts_pending() -> None:
    publication = _publication()

    assert publication.status is PublicationStatus.PENDING
    assert publication.attempts == 0
    assert publication.idempotency_key


def test_two_publications_never_share_an_idempotency_key() -> None:
    a, b = _publication(), _publication()

    assert a.idempotency_key != b.idempotency_key


def test_mark_publishing_then_mark_published() -> None:
    publication = _publication()
    publication.mark_publishing(now=_NOW)

    publication.mark_published(external_post_id="post-1", permalink="https://x", now=_NOW)

    assert publication.status is PublicationStatus.PUBLISHED
    assert publication.external_post_id == "post-1"
    assert publication.published_at == _NOW


def test_cannot_publish_without_first_marking_publishing() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)


def test_a_retryable_failed_attempt_reverts_to_pending_and_can_retry() -> None:
    publication = _publication()
    publication.mark_publishing(now=_NOW)
    original_key = publication.idempotency_key

    publication.record_attempt_failure(error="timeout", terminal=False, now=_NOW)

    assert publication.status is PublicationStatus.PENDING
    assert publication.attempts == 1
    assert publication.last_error == "timeout"
    assert publication.idempotency_key == original_key  # never regenerated

    # the retry self-loop: PENDING -> PUBLISHING again
    publication.mark_publishing(now=_NOW)
    assert publication.status is PublicationStatus.PUBLISHING


def test_a_terminal_failed_attempt_moves_to_failed() -> None:
    publication = _publication()
    publication.mark_publishing(now=_NOW)

    publication.record_attempt_failure(error="rejected", terminal=True, now=_NOW)

    assert publication.status is PublicationStatus.FAILED
    assert publication.attempts == 1


def test_cannot_mark_publishing_from_published() -> None:
    publication = _publication()
    publication.mark_publishing(now=_NOW)
    publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)

    with pytest.raises(ValidationError):
        publication.mark_publishing(now=_NOW)


def test_cannot_record_a_failure_outside_publishing() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.record_attempt_failure(error="x", terminal=False, now=_NOW)


def test_a_future_scheduled_at_starts_scheduled_not_pending() -> None:
    publication = Publication.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "hello", "media_asset_ids": [], "link": None},
        scheduled_at=_NOW + timedelta(days=1),
        now=_NOW,
    )

    assert publication.status is PublicationStatus.SCHEDULED


def test_a_past_scheduled_at_starts_pending_like_publish_now() -> None:
    publication = Publication.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "hello", "media_asset_ids": [], "link": None},
        scheduled_at=_NOW - timedelta(minutes=1),
        now=_NOW,
    )

    assert publication.status is PublicationStatus.PENDING


def test_release_for_publishing_moves_scheduled_to_pending() -> None:
    publication = Publication.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "hello", "media_asset_ids": [], "link": None},
        scheduled_at=_NOW + timedelta(days=1),
        now=_NOW,
    )

    publication.release_for_publishing(now=_NOW + timedelta(days=1))

    assert publication.status is PublicationStatus.PENDING


def test_cannot_release_a_publication_that_was_never_scheduled() -> None:
    publication = _publication()

    with pytest.raises(ValidationError):
        publication.release_for_publishing(now=_NOW)
