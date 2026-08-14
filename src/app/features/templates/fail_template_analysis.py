"""Records a provider-side analysis failure (D14's ``analysing ->
analysis_failed`` edge, retryable via ``CatalogTemplate.retry_analysis``).
Separate from ``CompleteTemplateAnalysis`` rather than an optional error
branch through it - the two take genuinely different inputs (a failure
reason string vs. a full analysis result) and neither needs the other's
placeholder-validation machinery.
"""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogTemplateId, TenantId


class FailTemplateAnalysis:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, template_id: CatalogTemplateId, reason: str
    ) -> CatalogTemplate:
        async with self._uow_factory(tenant_id) as uow:
            template = await uow.catalog_templates.get(tenant_id, template_id)
            if template is None:
                raise NotFoundError("Template not found.")

            now = self._clock.now()
            template.mark_analysis_failed(reason=reason, now=now)
            await uow.catalog_templates.update(template)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="catalog_template.analysis_failed",
                subject_type="catalog_template",
                subject_id=template.id,
                before={"status": "analysing"},
                after={"status": "analysis_failed", "reason": reason},
                now=now,
            )

            return template
