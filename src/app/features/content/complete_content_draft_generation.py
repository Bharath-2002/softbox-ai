"""Validates the `GeneratedCopy` `agents.copywriting` got from
`TextGeneration` against the tenant's forbidden-claims list
(`services.copy_validation.validate_copy`) and, if clean, creates the
`content_draft` row.

A validation failure **fails the task-queue job** rather than writing any
row — `entities.content_draft`'s single-member status enum has no state
for "generated but rejected," deliberately (see its own docstring and
`content_drafts`' migration docstring: the approval-gate chunk is what
will need to widen that vocabulary, not this one). Re-prompting the same
model for copy that violated a brand rule is more likely to succeed than
re-rolling a failed image is, so routing it through `TaskQueue.fail`'s
existing bounded-retry-then-dead ladder (the same one
`FailGenerationItemRender`/`FailCatalogImageQc`'s job-execution failures
use) is a deliberate reuse, not a shortcut — a brand-rule violation is
exactly as retryable as a transient provider error from this queue's point
of view.

If a live draft already exists for `(variant_id, channel, locale)`, this
is a regeneration: `mark_superseded` on the existing row, then `create()`
for the replacement, in that order, in this one transaction — the same
write order `CompleteGenerationItemRender` uses for `catalog_images`, for
the same reason (the partial unique index's non-deferred check forces
`UPDATE` before `INSERT`; see `entities.content_draft`'s docstring for the
full constraint-interaction reasoning).
"""

from __future__ import annotations

from uuid import UUID

from app.entities.content_draft import ContentDraft
from app.services.copy_prompt_composition import COPY_PROMPT_VERSION
from app.services.copy_validation import validate_copy
from app.services.ports.text_generation import GeneratedCopy
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import ProductVariantId, TenantId


class CompleteContentDraftGeneration:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        variant_id: ProductVariantId,
        channel: str,
        locale: str,
        job_id: UUID,
        copy: GeneratedCopy,
        forbidden_claims: list[str],
    ) -> ContentDraft | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            violation = validate_copy(copy, forbidden_claims=forbidden_claims)
            if violation is not None:
                await uow.task_queue.fail(tenant_id, job_id, error=violation, now=now)
                return None

            existing = await uow.content_drafts.get_live(
                tenant_id, variant_id, channel=channel, locale=locale
            )
            draft = ContentDraft.create(
                tenant_id,
                variant_id,
                channel=channel,
                locale=locale,
                title=copy.title,
                body=copy.body,
                hashtags=copy.hashtags,
                cta=copy.cta,
                alt_text=copy.alt_text,
                model=copy.model,
                prompt_version=COPY_PROMPT_VERSION,
                now=now,
            )
            if existing is not None:
                existing.mark_superseded(by=draft.id, now=now)
                await uow.content_drafts.update(existing)
            await uow.content_drafts.add(draft)

            await uow.task_queue.complete(tenant_id, job_id, now=now)
            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="content_draft.generated",
                subject_type="content_draft",
                subject_id=draft.id,
                before=None,
                after={"channel": channel, "locale": locale, "status": draft.status.value},
                now=now,
            )
            return draft
