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

`status` ships with a single member, `GENERATED` — deliberately not the
full `pending_approval`/`approved`/`rejected`/... vocabulary
`catalog_image`'s diagram-backed enum has from its first chunk. D23 gives
no authoritative state diagram for content drafts the way D18 does for
`catalog_image`, so naming states this chunk cannot drive would be the
same speculative-generic mistake the `workflow_runs` deferral avoided
earlier in this project. The copywriting agent and the approval-gate chunk
that actually produce and drive those transitions extend both this enum
and the migration's `CHECK` constraint when they land.

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
            edited_by=None,
            superseded_by=None,
            created_at=now,
            updated_at=now,
        )

    def mark_superseded(self, *, by: ContentDraftId, now: datetime) -> None:
        if self.superseded_by is not None:
            raise ValidationError(f"Content draft {self.id} is already superseded.")
        self.superseded_by = by
        self.updated_at = now
