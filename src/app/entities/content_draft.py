"""The current-state row per (variant, channel, locale) (D23) — copy is
subject to the same approval gate as imagery, so this follows
`entities.catalog_image`'s exact shape: a mutable current-state row plus
`superseded_by`, not an in-place-editable one.

That is load-bearing, not a stylistic match: D21's `publications` table
carries a `content_draft_id` FK. If a draft were mutable in place, editing
the copy of an already-published post would silently change what that FK
resolves to after the fact — the exact problem `catalog_images.superseded_by`
exists to prevent for imagery. So a later "manual copy editing" chunk will
mean `mark_superseded()` on the live row plus `create()` for the
replacement, in one transaction, the same two-write order
`CompleteGenerationItemRender`'s regeneration path already uses — see
`migrations/versions/28b3907984f5_add_content_drafts.py` for the full
constraint-interaction reasoning (`superseded_by`'s deferrable FK vs. the
partial unique index) and
`tests/infrastructure/test_content_draft_supersede.py` for the real-Postgres
proof.

`status` originally shipped with a single member, `GENERATED` — see
`migrations/versions/28b3907984f5_add_content_drafts.py` for why guessing
the rest early would have repeated the `workflow_runs` speculative-generic
mistake. `migrations/versions/e88d14230ad4_widen_content_draft_status.py`
widened it to the full vocabulary once the copywriting agent
(`features.content.complete_content_draft_generation`) and the approval
gate actually needed it: `GENERATED` (a freshly generated row, matching
`catalog_image.PENDING_QC`'s "just produced, nothing has acted on it yet"
role) -> `PENDING_APPROVAL` (`mark_pending_approval()`, mirroring
`mark_qc_passed`) -> `APPROVED`/`REJECTED`. Deliberately **not** collapsed
into `GENERATED` meaning "awaiting approval" — `catalog_image` never
collapsed `pending_qc`/`pending_approval` either, and the same reason
applies: a state a human is meant to act on needs its own name, so nothing
else can land there by sharing a value that meant something different (the
not-yet-built "manual copy editing" chunk's initial status, for one,
should not have to mean the same thing as "an LLM just produced this").

No committed row is observed at `GENERATED` today —
`features.content.complete_content_draft_generation.CompleteContentDraftGeneration`
calls `mark_pending_approval()` in the same transaction as `create()`, so
`GENERATED` never survives past that use case's commit. Any future writer
of a new draft row (the manual-copy-editing chunk, most notably) must do
the same, or the row it creates is unapprovable forever with no error
anywhere — exactly the dead end `human_review` catalog images are already
known to hit.

`channel`/`locale` are plain `str`, not domain enums — see the migration's
docstring for why (closer to tenant/deployment configuration than fixed
domain vocabulary).

`edited_by` means **"who authored this version,"** not "who last mutated
this row" — a consequence of supersede-not-mutate: editing a draft creates
a *new* row (via `create()` again, then `mark_superseded()` on the old
one), so there is no in-place mutation for `edited_by` to record. A human
edit stamps the replacement row's `edited_by` with the editor's `UserId`;
an agent-generated row's `edited_by` stays `None`. Not built yet — `create()`
always sets it `None` today — but the meaning is fixed now so the editing
chunk does not have to guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.errors import ValidationError
from app.shared.ids import ContentDraftId, ProductVariantId, TenantId, UserId, new_content_draft_id


class ContentDraftStatus(StrEnum):
    GENERATED = "generated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ContentDraft:
    id: ContentDraftId
    tenant_id: TenantId
    variant_id: ProductVariantId
    channel: str
    locale: str
    title: str | None
    body: str
    hashtags: list[str]
    cta: str | None
    alt_text: str
    model: str
    prompt_version: str
    status: ContentDraftStatus
    edited_by: UserId | None
    approved_by: UserId | None
    approved_at: datetime | None
    rejection_reason: str | None
    superseded_by: ContentDraftId | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        *,
        channel: str,
        locale: str,
        body: str,
        alt_text: str,
        model: str,
        prompt_version: str,
        now: datetime,
        title: str | None = None,
        hashtags: list[str] | None = None,
        cta: str | None = None,
        edited_by: UserId | None = None,
    ) -> ContentDraft:
        return ContentDraft(
            id=new_content_draft_id(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel=channel,
            locale=locale,
            title=title,
            body=body,
            hashtags=hashtags if hashtags is not None else [],
            cta=cta,
            alt_text=alt_text,
            model=model,
            prompt_version=prompt_version,
            status=ContentDraftStatus.GENERATED,
            edited_by=edited_by,
            approved_by=None,
            approved_at=None,
            rejection_reason=None,
            superseded_by=None,
            created_at=now,
            updated_at=now,
        )

    def mark_superseded(self, *, by: ContentDraftId, now: datetime) -> None:
        if self.superseded_by is not None:
            raise ValidationError(f"Content draft {self.id} is already superseded.")
        self.superseded_by = by
        self.updated_at = now

    def mark_pending_approval(self, *, now: datetime) -> None:
        """`generated -> pending_approval`, mirroring `catalog_image.mark_qc_passed`'s
        role: records that this row is ready for a human (or the
        `approval.required`-disabled auto-approve path) to act on."""
        if self.status != ContentDraftStatus.GENERATED:
            raise ValidationError(
                f"Cannot move to pending_approval from status {self.status.value!r}."
            )
        self.status = ContentDraftStatus.PENDING_APPROVAL
        self.updated_at = now

    def approve(self, *, approved_by: UserId | None, now: datetime) -> None:
        """`pending_approval -> approved`. `approved_by` is `None` only for
        the auto-approve path (`approval.required` resolved `False`) — a
        human-driven approval always passes a real `UserId`, the same
        `CatalogImage.approve` convention."""
        if self.status != ContentDraftStatus.PENDING_APPROVAL:
            raise ValidationError(f"Cannot approve from status {self.status.value!r}.")
        self.status = ContentDraftStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = now
        self.updated_at = now

    def reject(self, *, reason: str, now: datetime) -> None:
        """`pending_approval -> rejected`. Human-only, matching
        `CatalogImage.reject` — nothing in this codebase auto-rejects."""
        if self.status != ContentDraftStatus.PENDING_APPROVAL:
            raise ValidationError(f"Cannot reject from status {self.status.value!r}.")
        self.status = ContentDraftStatus.REJECTED
        self.rejection_reason = reason
        self.updated_at = now
