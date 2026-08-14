"""One row per attempted post to a channel (D21) — not a
current-state-plus-``superseded_by`` design like `catalog_image`/
`content_draft`: a publication *is* a specific post, and retrying it is
the same post trying again, not new content replacing old. See the
migration's own docstring for the full reasoning.

``idempotency_key`` is generated once, in `create()`, and never touched
again — the single fact the Gate's "a retry after a timeout does not
create a second post" property rests on. Nothing in this entity
regenerates it; a retry re-reads the same row and reuses the same key.

Five statuses, not `generation_item`'s five for the same reason (`pending
-> running -> succeeded` / `failed -> dead`) but a different vocabulary:
this entity collapses "failed, will retry" back into `PENDING` rather than
giving it its own transient `FAILED` state, because `attempts`/`last_error`
already carry the per-attempt history a merchant-facing publish record
needs — a distinct state here would describe nothing `attempts`/
`last_error` don't already say plainer. `FAILED` is reserved for the one
case that *is* worth a distinct terminal state: attempts exhausted
(`TaskQueue.fail` reporting the job went `dead`), where nothing will ever
retry this row again and a human needs to know that.

``SCHEDULED`` (added by `6e9ce80dab43_widen_publications_status`, see that
migration) is D21's "a `due_at` column plus a poller" — a `Publication`
created with a future `scheduled_at` starts here instead of `PENDING` and
writes no `publish_requested` outbox event yet; nothing is claimable by
`StartPublicationPublish` until `release_for_publishing()` moves it to
`PENDING` and the poller (`features.publishing.
release_scheduled_publications`) writes that event itself, in the same
transaction as the transition. Treated as "live" for the single-flight
guard exactly like `PENDING`/`PUBLISHING` — a second publish to the same
channel and variant must not slip in while the first is merely waiting for
its scheduled time.

``mark_publishing()`` accepts both `PENDING` (first attempt) and its own
prior `PENDING` after a reverted failed attempt (the retry self-loop) —
the same "claim, attempt, revert-or-advance" shape `GenerationItem.
mark_running` already established for `pending -> running` / `failed ->
running`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.shared.errors import ValidationError
from app.shared.ids import (
    ContentDraftId,
    ProductVariantId,
    PublicationId,
    SocialAccountId,
    TenantId,
    new_publication_id,
)


class PublicationStatus(StrEnum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class Publication:
    id: PublicationId
    tenant_id: TenantId
    variant_id: ProductVariantId
    channel_id: SocialAccountId
    content_draft_id: ContentDraftId | None
    idempotency_key: str
    status: PublicationStatus
    scheduled_at: datetime | None
    published_at: datetime | None
    external_post_id: str | None
    permalink: str | None
    payload: dict[str, Any]
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        channel_id: SocialAccountId,
        *,
        content_draft_id: ContentDraftId | None,
        payload: dict[str, Any],
        scheduled_at: datetime | None = None,
        now: datetime,
    ) -> Publication:
        status = (
            PublicationStatus.SCHEDULED
            if scheduled_at is not None and scheduled_at > now
            else PublicationStatus.PENDING
        )
        return Publication(
            id=new_publication_id(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=content_draft_id,
            idempotency_key=uuid4().hex,
            status=status,
            scheduled_at=scheduled_at,
            published_at=None,
            external_post_id=None,
            permalink=None,
            payload=payload,
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )

    def release_for_publishing(self, *, now: datetime) -> None:
        """`SCHEDULED -> PENDING`, called by the poller once `scheduled_at`
        is due. Distinct from `mark_publishing()`: this makes the row
        claimable, it does not itself claim it — `StartPublicationPublish`
        still does that, same as for a publication that was never
        scheduled at all."""
        if self.status != PublicationStatus.SCHEDULED:
            raise ValidationError(f"Cannot release from status {self.status.value!r}.")
        self.status = PublicationStatus.PENDING
        self.updated_at = now

    def mark_publishing(self, *, now: datetime) -> None:
        if self.status != PublicationStatus.PENDING:
            raise ValidationError(f"Cannot start publishing from status {self.status.value!r}.")
        self.status = PublicationStatus.PUBLISHING
        self.updated_at = now

    def mark_published(
        self, *, external_post_id: str, permalink: str | None, now: datetime
    ) -> None:
        if self.status != PublicationStatus.PUBLISHING:
            raise ValidationError(f"Cannot publish from status {self.status.value!r}.")
        self.status = PublicationStatus.PUBLISHED
        self.external_post_id = external_post_id
        self.permalink = permalink
        self.published_at = now
        self.updated_at = now

    def record_attempt_failure(self, *, error: str, terminal: bool, now: datetime) -> None:
        """Called once per failed attempt, whether or not `TaskQueue` will
        retry it. `terminal=True` (the job came back `dead`) is the only
        case that also moves `status` — otherwise this reverts to
        `PENDING` so the next attempt can call `mark_publishing()` again,
        the retry self-loop described in this module's own docstring."""
        if self.status != PublicationStatus.PUBLISHING:
            raise ValidationError(f"Cannot fail from status {self.status.value!r}.")
        self.attempts += 1
        self.last_error = error
        self.status = PublicationStatus.FAILED if terminal else PublicationStatus.PENDING
        self.updated_at = now

    def defer(self, *, reason: str, now: datetime) -> None:
        """A rate-limited attempt, not a failed one: reverts to `PENDING`
        for a later retry the same way `record_attempt_failure` does, but
        deliberately does **not** increment `attempts` — see
        `features.publishing.defer_publication_publish`'s docstring for
        why consuming a bounded retry on every rate-limit rejection would
        let a channel at its daily cap lose every queued publish for the
        rest of the day, permanently."""
        if self.status != PublicationStatus.PUBLISHING:
            raise ValidationError(f"Cannot defer from status {self.status.value!r}.")
        self.last_error = reason
        self.status = PublicationStatus.PENDING
        self.updated_at = now
