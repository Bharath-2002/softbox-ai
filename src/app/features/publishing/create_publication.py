"""Commits a `publications` row and its `idempotency_key` **in the same
transaction**, then writes a `publication.publish_requested` outbox event —
the same "real capability, no automatic trigger" posture every other queue
entry point in this codebase uses. This is the transaction the Gate's "the
idempotency key is committed before the external call" property depends
on: nothing in this use case ever calls `ChannelPublisher`, so the key is
durably committed and this call has already returned long before any
provider is contacted, by construction, not by a runtime check.

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
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraftStatus
from app.entities.publication import Publication
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import AssetId, ContentDraftId, ProductVariantId, SocialAccountId, TenantId

_EVENT_TYPE = "publication.publish_requested"


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
                now=now,
            )
            await uow.publications.add(publication)

            await uow.outbox_events.add(
                tenant_id,
                event_type=_EVENT_TYPE,
                payload={"publication_id": str(publication.id)},
                now=now,
            )

            return publication
