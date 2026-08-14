"""Manual copy editing (D23) — the "editing creates a new row via
``mark_superseded`` + ``create()``" design `entities.content_draft`'s own
docstring already promised, now built. A human editor's changes replace
the live row for ``(variant_id, channel, locale)``, never mutate it in
place, for the same reason `CompleteContentDraftGeneration`'s regeneration
path does not: D21's ``publications.content_draft_id`` FK must not
silently repoint if the row it points at were editable in place.

Runs the same two checks generation does, so a human editor cannot bypass
either M6 Gate criterion just because no LLM was involved this time:

- `services.copy_validation.validate_copy` against the tenant's
  ``content.forbidden_claims`` setting. Unlike
  `CompleteContentDraftGeneration`, there is no queue job to fail here — a
  violation raises `ValidationError`, surfaced to the editor as a 4xx so
  they can fix the text and resubmit, rather than being dead-lettered.
- ``approval.required``, resolved the same way, same ``is False``
  fail-closed check, same auto-approve-when-disabled behaviour. An edit is
  exactly as subject to the approval gate as a fresh generation.

The replacement row's ``model``/``prompt_version`` are carried forward
from the row being edited, not set to a "manual" sentinel — those two
columns describe the generation this content descends from, and a human
edit does not produce a new one; inventing a sentinel would make them look
like provenance data that no generation ever produced. ``edited_by`` is
stamped with the editor's `UserId` on the replacement row (see
`entities.content_draft`'s docstring for why this is a new-row field, not
an in-place mutation record).

The audit log entry is written against the **replacement** row's id, not
the superseded one — the same choice `CompleteContentDraftGeneration`
already makes for regeneration. A `list_for_subject` query against the
superseded row's id sees nothing; that history lives on the new row's
`before`. Consistent with existing precedent, not an oversight specific to
this chunk.
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.features.content.start_content_draft_generation import resolve_forbidden_claims
from app.services.copy_validation import validate_copy
from app.services.ports.text_generation import GeneratedCopy
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.settings_resolver import SettingsResolver
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import ContentDraftId, TenantId, UserId

_APPROVAL_REQUIRED_KEY = "approval.required"
_FORBIDDEN_CLAIMS_KEY = "content.forbidden_claims"


class EditContentDraft:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        draft_id: ContentDraftId,
        edited_by: UserId,
        title: str | None,
        body: str,
        hashtags: list[str],
        cta: str | None,
        alt_text: str,
    ) -> ContentDraft:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            existing = await uow.content_drafts.get(tenant_id, draft_id)
            if existing is None:
                raise NotFoundError("Content draft not found.")
            if existing.superseded_by is not None:
                raise ValidationError(
                    "Cannot edit a superseded content draft; edit the live draft instead."
                )

            variant = await uow.product_variants.get(tenant_id, existing.variant_id)
            if variant is None:
                raise NotFoundError("Product variant not found.")
            product = await uow.products.get(tenant_id, variant.product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            resolver = SettingsResolver(uow.settings, uow.categories)
            raw_forbidden_claims = await resolver.resolve(
                tenant_id,
                _FORBIDDEN_CLAIMS_KEY,
                category_id=product.category_id,
                product_id=product.id,
            )
            forbidden_claims = resolve_forbidden_claims(raw_forbidden_claims)

            candidate = GeneratedCopy(
                title=title,
                body=body,
                hashtags=hashtags,
                cta=cta,
                alt_text=alt_text,
                model=existing.model,
                cost_micros=0,
                latency_ms=0,
            )
            violation = validate_copy(candidate, forbidden_claims=forbidden_claims)
            if violation is not None:
                raise ValidationError(violation)

            draft = ContentDraft.create(
                tenant_id,
                existing.variant_id,
                channel=existing.channel,
                locale=existing.locale,
                title=title,
                body=body,
                hashtags=hashtags,
                cta=cta,
                alt_text=alt_text,
                model=existing.model,
                prompt_version=existing.prompt_version,
                now=now,
                edited_by=edited_by,
            )
            draft.mark_pending_approval(now=now)

            approval_required = await resolver.resolve(
                tenant_id,
                _APPROVAL_REQUIRED_KEY,
                category_id=product.category_id,
                product_id=product.id,
            )
            if approval_required is False:
                draft.approve(approved_by=None, now=now)

            existing.mark_superseded(by=draft.id, now=now)
            await uow.content_drafts.update(existing)
            await uow.content_drafts.add(draft)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=edited_by,
                action="content_draft.edited",
                subject_type="content_draft",
                subject_id=draft.id,
                before={"status": existing.status.value, "body": existing.body},
                after={"status": draft.status.value, "body": draft.body},
                now=now,
            )
            return draft
