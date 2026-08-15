"""Commits a `publications` row and its `idempotency_key` **in the same
transaction** — this is the transaction the Gate's "the idempotency key is
committed before the external call" property depends on: nothing in this
use case ever calls `ChannelPublisher`, so the key is durably committed
and this call has already returned long before any provider is contacted,
by construction, not by a runtime check.

Every publication starts `SCHEDULED` (see `entities.publication`'s
docstring) and this use case writes **no** `publish_requested` outbox
event, unlike the version that shipped before `docs/DIAGRAMS.md`'s own
Publication diagram was checked — that version enqueued immediately for a
`due_at` that was already due, which is exactly the "hand a task queue a
schedule to keep" shape D21 warns against. The `due_at` poller
(`features.publishing.release_scheduled_publications`) is now the *only*
thing that ever makes a row claimable, whether its `due_at` was "now" (an
immediate publish request) or genuinely in the future — one mechanism,
not two.

`content_draft_id` is optional (see the migration's docstring for why) but
when given must resolve to a **live, approved** draft — publishing
unapproved copy is exactly what D23's approval gate exists to prevent, and
allowing a `pending_approval`/`rejected` draft's `caption` into a public
post would be that gate silently bypassed one layer up.

`media_asset_ids` is caller-supplied rather than auto-derived from the
variant's approved catalog images — the same scope cut
`GenerateContentDraft` already made for `channel`/`locale`: there is no
per-channel "which images are the ones to post" rule anywhere in this
codebase to derive it from automatically.

D21's single-flight requirement ("a lock per account, variant") is enforced
here as a `get_live` pre-check raising `ConflictError` for the common case,
backed by the migration's partial unique index
(`ix_publications_live_per_channel_variant`) for the check-then-act race
between two concurrent calls — the same "app-level check, DB-level
backstop" split D15's `uq_category_spec_versions_tenant_category_version`
established. A publication is "live" while `scheduled`, `dispatching` or
`failed`; a second publish to the same channel for the same variant is
fine once the first has reached `published`, `dead` or `cancelled`.
"""

from __future__ import annotations

from datetime import datetime

from app.entities.content_draft import ContentDraftStatus
from app.entities.publication import Publication
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import ConflictError, NotFoundError, ValidationError
from app.shared.ids import AssetId, ContentDraftId, ProductVariantId, SocialAccountId, TenantId


class CreatePublication:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        channel_id: SocialAccountId,
        content_draft_id: ContentDraftId | None,
        caption: str,
        media_asset_ids: list[AssetId],
        link: str | None = None,
        due_at: datetime | None = None,
    ) -> Publication:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            variant = await uow.product_variants.get(tenant_id, variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")

            channel = await uow.social_accounts.get(tenant_id, channel_id)
            if channel is None:
                raise NotFoundError("Channel account not found.")

            if content_draft_id is not None:
                draft = await uow.content_drafts.get(tenant_id, content_draft_id)
                if draft is None:
                    raise NotFoundError("Content draft not found.")
                if draft.superseded_by is not None or draft.status != ContentDraftStatus.APPROVED:
                    raise ValidationError("Cannot publish from an unapproved content draft.")

            if not media_asset_ids:
                raise ValidationError("A publication needs at least one media asset.")

            live = await uow.publications.get_live(tenant_id, variant_id, channel_id)
            if live is not None:
                raise ConflictError(
                    "A publication for this variant and channel is already in flight."
                )

            publication = Publication.create(
                tenant_id,
                variant_id,
                channel_id,
                content_draft_id=content_draft_id,
                payload={
                    "caption": caption,
                    "media_asset_ids": [str(a) for a in media_asset_ids],
                    "link": link,
                },
                due_at=due_at,
                now=now,
            )
            await uow.publications.add(publication)

            return publication
