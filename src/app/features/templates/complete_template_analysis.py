"""Finishes a template analysis: re-fetches the template inside its own
transaction (never trusting the row ``agents.template_analysis`` carried
across its provider call — a concurrent retry or archive could have moved
it since ``StartTemplateAnalysis`` committed), resolves the category's
*current live* spec (``SpecSnapshotBuilder``, not a specific published
version — a template must keep validating against whatever the category's
definitions are today, not go stale against a version from whenever it was
last analysed), runs D14a's placeholder validator, and lands the template
on ``analysed`` or ``invalid``.
"""

from __future__ import annotations

from typing import Any

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_snapshot_builder import SpecSnapshotBuilder
from app.services.template_placeholder_validator import validate_template_placeholders
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogTemplateId, CategoryId, TenantId


class CompleteTemplateAnalysis:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        template_id: CatalogTemplateId,
        category_id: CategoryId,
        analysis: dict[str, Any] | None,
        prompt_template: str,
        analysis_model: str | None,
    ) -> CatalogTemplate:
        async with self._uow_factory(tenant_id) as uow:
            template = await uow.catalog_templates.get(tenant_id, template_id)
            if template is None:
                raise NotFoundError("Template not found.")

            snapshot_builder = SpecSnapshotBuilder(
                uow.categories,
                uow.attribute_definitions,
                uow.variant_axes,
                uow.variant_axis_values,
                uow.input_image_slots,
                uow.catalog_image_slots,
                uow.catalog_slot_input_requirements,
            )
            snapshot = await snapshot_builder.build(tenant_id, category_id)
            problems = validate_template_placeholders(
                snapshot,
                catalog_image_slot_id=str(template.catalog_image_slot_id),
                prompt_template=prompt_template,
            )

            now = self._clock.now()
            before_status = template.status.value
            if problems:
                template.mark_invalid(reason="; ".join(problems), now=now)
            else:
                template.mark_analysed(
                    prompt_template=prompt_template,
                    analysis=analysis,
                    analysis_model=analysis_model,
                    now=now,
                )
            await uow.catalog_templates.update(template)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=None,
                action="catalog_template.analysis_completed",
                subject_type="catalog_template",
                subject_id=template.id,
                before={"status": before_status},
                after={"status": template.status.value},
                now=now,
            )

            return template
