"""One row per attempted post to a channel (D21) — not a
current-state-plus-``superseded_by`` design like `catalog_image`/
`content_draft`: a publication *is* a specific post, and retrying it is
the same post trying again, not new content replacing old. See the
migration's own docstring for the full reasoning.

``idempotency_key`` is generated once, in `create()`, and never touched
again — the single fact the Gate's "a retry after a timeout does not
create a second post" property rests on. Nothing in this entity
regenerates it; a retry re-reads the same row and reuses the same key.

Six statuses, matching `docs/DIAGRAMS.md`'s own Publication state diagram
exactly (`scheduled -> dispatching -> published`, `dispatching ->
failed -> dispatching`, `failed -> dead`, `scheduled -> cancelled`) —
**not** the five-value collapsed vocabulary the previous two migrations
shipped from D21's prose sketch alone, before this entity's own diagram
was checked. That earlier design deliberately collapsed "failed, will
retry" back into a single waiting state; the diagram disagrees and gives
`failed` its own transient state, matching `generation_item`'s shape
instead. Reworked in one migration (`e563d43d40b4`) rather than left to
drift, per user decision after the mismatch was found.

``create()`` always starts a row `SCHEDULED` — there is no separate
"publish now" status. `due_at` defaults to `now` when the caller gives
none, so an immediate publish is simply a `due_at` that is already due;
the `due_at` poller (`features.publishing.
release_scheduled_publications`) is the *only* thing that ever makes a
`SCHEDULED` row claimable, whether it was due immediately or scheduled
for later — matching D21's own warning that a task queue does not
schedule reliably across restarts and redeploys, so nothing here ever
hands `TaskQueue.enqueue()` a future `run_at` directly. Treated as "live"
for the single-flight guard, same as `DISPATCHING` and `FAILED` (still
in flight, still trying) — `PUBLISHED`/`DEAD`/`CANCELLED` are all
terminal and are not.

``mark_dispatching()`` accepts both `SCHEDULED` (the poller found it due)
and `FAILED` (a retry, driven by `TaskQueue`'s own backoff-rescheduled
job — **not** by the `due_at` poller; a retry never goes back through
`scheduled`) — the same "claim, attempt, revert-or-advance" shape
`GenerationItem.mark_running` already established for `pending -> running`
/ `failed -> running`.

``record_attempt_failure(terminal=False)`` moves to `FAILED`, a distinct
transient state (not a revert to `SCHEDULED`) — `attempts`/`last_error`
already carry the per-attempt history, but the *state itself* now names
"has failed, will retry" rather than folding it back into "not yet
tried," matching the diagram.

``defer()`` (rate-limited, not failed — see this module's own docstring
on that split before) moves `DISPATCHING -> SCHEDULED` and pushes `due_at`
forward to the deferred time, rather than directly re-enqueueing a
`TaskQueue` job the way the pre-rework version did — that was exactly the
"schedule via a future `run_at`" anti-pattern D21 warns against, just for
the defer case instead of the first attempt. The `due_at` poller picks the
row back up once its new `due_at` is reached, the same as any other
`SCHEDULED` row; see `features.publishing.defer_publication_publish`'s
own docstring for the accepted "no terminal state for a permanently
unsatisfiable limit" tradeoff, which still applies unchanged.

``cancel()`` is `SCHEDULED -> CANCELLED` only, per the diagram
(`scheduled --> cancelled`) — a publication already `DISPATCHING` or
later cannot be cancelled, since a provider call may already be in
flight or done.
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
    DISPATCHING = "dispatching"
    PUBLISHED = "published"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


@dataclass
class Publication:
    id: PublicationId
    tenant_id: TenantId
    variant_id: ProductVariantId
    channel_id: SocialAccountId
    content_draft_id: ContentDraftId | None
    idempotency_key: str
    status: PublicationStatus
    due_at: datetime
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
        due_at: datetime | None = None,
        now: datetime,
    ) -> Publication:
        return Publication(
            id=new_publication_id(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=content_draft_id,
            idempotency_key=uuid4().hex,
            status=PublicationStatus.SCHEDULED,
            due_at=due_at if due_at is not None else now,
            published_at=None,
            external_post_id=None,
            permalink=None,
            payload=payload,
            attempts=0,
            last_error=None,
            created_at=now,
            updated_at=now,
        )

    def defer_dispatch(self, *, until: datetime, now: datetime) -> None:
        """Pushes `due_at` forward without changing `status` — used by
        `features.publishing.release_scheduled_publications` as the guard
        against a second sweep re-enqueueing the same still-`SCHEDULED`
        row before the first job it created has been claimed. Not a state
        transition; `status` stays `SCHEDULED` throughout, which is why
        this is a distinct method from `defer()` (rate-limited mid-attempt,
        `DISPATCHING -> SCHEDULED`) rather than a shared one."""
        if self.status != PublicationStatus.SCHEDULED:
            raise ValidationError(f"Cannot defer dispatch from status {self.status.value!r}.")
        self.due_at = until
        self.updated_at = now

    def mark_dispatching(self, *, now: datetime) -> None:
        if self.status not in (PublicationStatus.SCHEDULED, PublicationStatus.FAILED):
            raise ValidationError(f"Cannot start dispatching from status {self.status.value!r}.")
        self.status = PublicationStatus.DISPATCHING
        self.updated_at = now

    def mark_published(
        self, *, external_post_id: str, permalink: str | None, now: datetime
    ) -> None:
        if self.status != PublicationStatus.DISPATCHING:
            raise ValidationError(f"Cannot publish from status {self.status.value!r}.")
        self.status = PublicationStatus.PUBLISHED
        self.external_post_id = external_post_id
        self.permalink = permalink
        self.published_at = now
        self.updated_at = now

    def record_attempt_failure(self, *, error: str, terminal: bool, now: datetime) -> None:
        """Called once per failed attempt, whether or not `TaskQueue` will
        retry it. `terminal=True` (the job came back `dead`) moves to the
        terminal `DEAD` state; otherwise `FAILED`, the transient
        retry-pending state this module's own docstring explains."""
        if self.status != PublicationStatus.DISPATCHING:
            raise ValidationError(f"Cannot fail from status {self.status.value!r}.")
        self.attempts += 1
        self.last_error = error
        self.status = PublicationStatus.DEAD if terminal else PublicationStatus.FAILED
        self.updated_at = now

    def defer(self, *, reason: str, due_at: datetime, now: datetime) -> None:
        """A rate-limited attempt, not a failed one: reverts to
        `SCHEDULED` with `due_at` pushed to the deferred time, but
        deliberately does **not** increment `attempts` — see
        `features.publishing.defer_publication_publish`'s docstring for
        why consuming a bounded retry on every rate-limit rejection would
        let a channel at its daily cap lose every queued publish for the
        rest of the day, permanently."""
        if self.status != PublicationStatus.DISPATCHING:
            raise ValidationError(f"Cannot defer from status {self.status.value!r}.")
        self.last_error = reason
        self.status = PublicationStatus.SCHEDULED
        self.due_at = due_at
        self.updated_at = now

    def cancel(self, *, now: datetime) -> None:
        if self.status != PublicationStatus.SCHEDULED:
            raise ValidationError(f"Cannot cancel from status {self.status.value!r}.")
        self.status = PublicationStatus.CANCELLED
        self.updated_at = now
