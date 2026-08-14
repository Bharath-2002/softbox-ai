"""Human-driven approval (M6) — `pending_approval -> approved`, the
counterpart to `complete_content_draft_generation`'s auto-approve branch.
Always passes a real `approved_by`, unlike that branch's `None` for the
setting-driven path. Mirrors `features.generation.approve_catalog_image`
exactly — the same approval gate, D23 says, so the same shape.
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import ContentDraftId, TenantId, UserId


class ApproveContentDraft:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, draft_id: ContentDraftId, approved_by: UserId
    ) -> ContentDraft:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            draft = await uow.content_drafts.get(tenant_id, draft_id)
            if draft is None:
                raise NotFoundError("Content draft not found.")

            before_status = draft.status.value
            draft.approve(approved_by=approved_by, now=now)
            await uow.content_drafts.update(draft)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=approved_by,
                action="content_draft.approved",
                subject_type="content_draft",
                subject_id=draft_id,
                before={"status": before_status},
                after={"status": draft.status.value},
                now=now,
            )

            return draft
