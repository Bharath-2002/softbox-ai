"""Archives an ``analysed`` template (D14's terminal state — the entity
rejects archiving from any other status)."""

from __future__ import annotations

from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CatalogTemplateId, TenantId


class ArchiveTemplate:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, template_id: CatalogTemplateId
    ) -> CatalogTemplate:
        async with self._uow_factory(tenant_id) as uow:
            template = await uow.catalog_templates.get(tenant_id, template_id)
            if template is None:
                raise NotFoundError("Template not found.")

            template.archive(now=self._clock.now())
            await uow.catalog_templates.update(template)

            return template
