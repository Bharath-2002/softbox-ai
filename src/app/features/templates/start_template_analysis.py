"""Transitions a template ``uploaded -> analysing`` (D14's state machine)
and hands back everything ``agents.template_analysis`` needs for the
provider call it makes *outside* this transaction: where the reference
image lives (``storage_key``/``mime``, read from the template's
``source_asset_id`` while a transaction is already open, rather than a
second use case just to look that up) and which category to resolve the
spec against (from the catalog image slot the template belongs to).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.entities.catalog_template import TemplateKind
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import CatalogTemplateId, CategoryId, TenantId


@dataclass(frozen=True)
class TemplateAnalysisContext:
    template_id: CatalogTemplateId
    category_id: CategoryId
    storage_key: str
    mime: str


class StartTemplateAnalysis:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, template_id: CatalogTemplateId
    ) -> TemplateAnalysisContext:
        async with self._uow_factory(tenant_id) as uow:
            template = await uow.catalog_templates.get(tenant_id, template_id)
            if template is None:
                raise NotFoundError("Template not found.")
            if template.kind != TemplateKind.ANALYSED_IMAGE or template.source_asset_id is None:
                raise ValidationError(
                    "Only an analysed_image template with a source asset can be analysed."
                )

            catalog_slot = await uow.catalog_image_slots.get(
                tenant_id, template.catalog_image_slot_id
            )
            if catalog_slot is None:
                raise NotFoundError("Catalog image slot not found.")

            asset = await uow.assets.get(tenant_id, template.source_asset_id)
            if asset is None:
                raise NotFoundError("Source asset not found.")

            template.start_analysing(now=self._clock.now())
            await uow.catalog_templates.update(template)

            return TemplateAnalysisContext(
                template_id=template.id,
                category_id=catalog_slot.category_id,
                storage_key=asset.storage_key,
                mime=asset.mime,
            )
