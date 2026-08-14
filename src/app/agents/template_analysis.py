"""Orchestrates D14's template analysis: calls the vision provider between
two independent transactions, owning neither itself. CLAUDE.md §5 - "one
use case, one transaction" - is a flat rule every existing use case follows;
an agent that opened its own ``UnitOfWork`` would be a second way to own
one, and this is the first agent this codebase has ever had, so the
precedent set here is the one M5's generation pipeline and M6's copywriting
agent inherit. ``StartTemplateAnalysis``/``CompleteTemplateAnalysis``/
``FailTemplateAnalysis`` each own exactly one transaction; this class owns
the control flow and the one call to ``VisionAnalysis`` that must not
happen inside either.
"""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.features.templates.complete_template_analysis import CompleteTemplateAnalysis
from app.features.templates.fail_template_analysis import FailTemplateAnalysis
from app.features.templates.start_template_analysis import StartTemplateAnalysis
from app.services.ports.object_storage import ObjectStorage
from app.services.ports.vision_analysis import VisionAnalysis
from app.shared.ids import CatalogTemplateId, TenantId


class TemplateAnalysisAgent:
    def __init__(
        self,
        start: StartTemplateAnalysis,
        complete: CompleteTemplateAnalysis,
        fail: FailTemplateAnalysis,
        object_storage: ObjectStorage,
        vision_analysis: VisionAnalysis,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._object_storage = object_storage
        self._vision_analysis = vision_analysis

    async def run(self, *, tenant_id: TenantId, template_id: CatalogTemplateId) -> CatalogTemplate:
        ctx = await self._start(tenant_id=tenant_id, template_id=template_id)

        try:
            image_bytes = await self._object_storage.read(ctx.storage_key)
            result = await self._vision_analysis.analyse_template(image_bytes, mime=ctx.mime)
        except Exception as exc:  # any provider/storage failure is retryable, not fatal
            return await self._fail(
                tenant_id=tenant_id, template_id=ctx.template_id, reason=str(exc)
            )

        return await self._complete(
            tenant_id=tenant_id,
            template_id=ctx.template_id,
            category_id=ctx.category_id,
            analysis=result.analysis,
            prompt_template=result.prompt_template,
            analysis_model=result.model,
        )
