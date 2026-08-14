"""Human-driven rejection (M6) — `pending_approval -> rejected`. Nothing in
this codebase auto-rejects, unlike `approve()`'s setting-driven path in
`complete_content_draft_generation` — a rejection always has a human reason
and a human actor. Mirrors `features.generation.reject_catalog_image`
exactly.
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import ContentDraftId, TenantId, UserId


class RejectContentDraft:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        draft_id: ContentDraftId,
        reason: str,
        rejected_by: UserId,
    ) -> ContentDraft:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            draft = await uow.content_drafts.get(tenant_id, draft_id)
            if draft is None:
                raise NotFoundError("Content draft not found.")

            before_status = draft.status.value
            draft.reject(reason=reason, now=now)
            await uow.content_drafts.update(draft)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=rejected_by,
                action="content_draft.rejected",
                subject_type="content_draft",
                subject_id=draft_id,
                before={"status": before_status},
                after={"status": draft.status.value, "rejection_reason": reason},
                now=now,
            )

            return draft
