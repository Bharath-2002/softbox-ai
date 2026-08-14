"""One row per attempted post to a channel (D21) — not a
current-state-plus-``superseded_by`` design like `catalog_image`/
`content_draft`: a publication *is* a specific post, and retrying it is
the same post trying again, not new content replacing old. See the
migration's own docstring for the full reasoning.

``idempotency_key`` is generated once, in `create()`, and never touched
again — the single fact the Gate's "a retry after a timeout does not
create a second post" property rests on. Nothing in this entity
regenerates it; a retry re-reads the same row and reuses the same key.

Four statuses, not `generation_item`'s five (`pending -> running ->
succeeded` / `failed -> dead`): this entity collapses "failed, will retry"
back into `PENDING` rather than giving it its own transient `FAILED` state,
because `attempts`/`last_error` already carry the per-attempt history a
merchant-facing publish record needs — a fifth state here would describe
nothing `attempts`/`last_error` don't already say plainer. `FAILED` is
reserved for the one case that *is* worth a distinct terminal state:
attempts exhausted (`TaskQueue.fail` reporting the job went `dead`), where
nothing will ever retry this row again and a human needs to know that.

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
        return Publication(
            id=new_publication_id(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=content_draft_id,
            idempotency_key=uuid4().hex,
            status=PublicationStatus.PENDING,
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
