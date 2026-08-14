"""Orchestrates D23's copy generation step: claims one due
`content_draft.generate_requested` job and calls the text-generation
provider *between* two independent transactions, then completes or fails
it — the same "agent owns the control flow and the one call that must not
happen inside a transaction, not a transaction itself" shape
`agents.generation_render`/`agents.catalog_image_qc` established first.

`run()` returns `None` when nothing was claimable (an ordinary empty poll)
so a caller (an admin trigger route, same as every other worker in this
codebase) can distinguish "nothing to do right now" from "did work."
Returns `None` on a validation failure too — `CompleteContentDraftGeneration`
already routed that through `TaskQueue.fail` and there is no `ContentDraft`
to hand back, the same "not every non-empty poll produces a row" shape
`CompleteCatalogImageQc`'s fail branch has.
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.features.content.complete_content_draft_generation import (
    CompleteContentDraftGeneration,
)
from app.features.content.fail_content_draft_generation import FailContentDraftGeneration
from app.features.content.start_content_draft_generation import StartContentDraftGeneration
from app.services.ports.text_generation import TextGeneration
from app.shared.ids import TenantId


class CopywritingAgent:
    def __init__(
        self,
        start: StartContentDraftGeneration,
        complete: CompleteContentDraftGeneration,
        fail: FailContentDraftGeneration,
        text_generation: TextGeneration,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._text_generation = text_generation

    async def run(self, *, tenant_id: TenantId) -> ContentDraft | None:
        ctx = await self._start(tenant_id=tenant_id)
        if ctx is None:
            return None

        try:
            copy = await self._text_generation.generate_copy(ctx.prompt, model=ctx.model, params={})
        except Exception as exc:  # any provider failure is retryable, not fatal
            await self._fail(
                tenant_id=tenant_id,
                job_id=ctx.job_id,
                error_code=type(exc).__name__,
                error_detail=str(exc),
            )
            return None

        return await self._complete(
            tenant_id=tenant_id,
            variant_id=ctx.variant_id,
            channel=ctx.channel,
            locale=ctx.locale,
            job_id=ctx.job_id,
            copy=copy,
            forbidden_claims=ctx.forbidden_claims,
        )
