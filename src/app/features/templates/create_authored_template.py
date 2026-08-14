"""Creates an ``authored_scene`` template (D14, D0's resolution) — a human
writes ``prompt_template`` directly, no reference photo or vision call
needed. This is what the stock scene preset library is entirely made of,
and the one template-creation path that is fully functional today with no
provider credentials.

Still passes through ``ANALYSING`` on the way to ``analysed``/``invalid``
rather than adding a state-machine bypass edge just for this kind — both
calls cost nothing in the same transaction, and every template's history
reads the same way regardless of which path produced it.

One transaction, matching every other use case (CLAUDE.md §5) — unlike the
``analysed_image`` path, there is no provider call here to keep out of it,
so this does not need the agent/three-use-case split ``TemplateAnalysisAgent``
uses.
"""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_snapshot_builder import SpecSnapshotBuilder
from app.services.template_placeholder_validator import validate_template_placeholders
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogImageSlotId, TenantId, UserId


class CreateAuthoredTemplate:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        name: str,
        prompt_template: str,
        actor_user_id: UserId,
    ) -> CatalogTemplate:
        async with self._uow_factory(tenant_id) as uow:
            catalog_slot = await uow.catalog_image_slots.get(tenant_id, catalog_image_slot_id)
            if catalog_slot is None:
                raise NotFoundError("Catalog image slot not found.")

            existing = await uow.catalog_templates.get_latest_version(
                tenant_id, catalog_image_slot_id, name
            )
            version = existing.version + 1 if existing is not None else 1

            now = self._clock.now()
            template = CatalogTemplate.create_authored(
                tenant_id,
                catalog_image_slot_id,
                name=name,
                prompt_template=prompt_template,
                created_by=actor_user_id,
                now=now,
                version=version,
            )
            await uow.catalog_templates.add(template)

            snapshot_builder = SpecSnapshotBuilder(
                uow.categories,
                uow.attribute_definitions,
                uow.variant_axes,
                uow.variant_axis_values,
                uow.input_image_slots,
                uow.catalog_image_slots,
                uow.catalog_slot_input_requirements,
            )
            snapshot = await snapshot_builder.build(tenant_id, catalog_slot.category_id)
            problems = validate_template_placeholders(
                snapshot,
                catalog_image_slot_id=str(catalog_image_slot_id),
                prompt_template=prompt_template,
            )

            template.start_analysing(now=now)
            if problems:
                template.mark_invalid(reason="; ".join(problems), now=now)
            else:
                template.mark_analysed(
                    prompt_template=prompt_template, analysis=None, analysis_model=None, now=now
                )
            await uow.catalog_templates.update(template)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_template.created",
                subject_type="catalog_template",
                subject_id=template.id,
                before=None,
                after={
                    "kind": "authored_scene",
                    "status": template.status.value,
                    "version": version,
                },
                now=now,
            )

            return template
