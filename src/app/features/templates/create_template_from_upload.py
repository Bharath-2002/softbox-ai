"""Creates an ``analysed_image`` template row from an already-verified
upload (``VerifyAndRegisterUpload`` must have run first — this takes an
existing ``Asset.id``, it never touches bytes itself). Lands in
``uploaded``; a separate call to ``TemplateAnalysisAgent`` (triggered by
its own admin route, not this one) is what moves it to ``analysing``.
Kept as two steps rather than triggering analysis inline here because the
agent makes a provider call this use case's single transaction must not be
holding open for (CLAUDE.md §5).
"""

from __future__ import annotations

from app.entities.asset import AssetKind
from app.entities.catalog_template import CatalogTemplate
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import AssetId, CatalogImageSlotId, TenantId, UserId


class CreateTemplateFromUpload:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        name: str,
        source_asset_id: AssetId,
        actor_user_id: UserId,
    ) -> CatalogTemplate:
        async with self._uow_factory(tenant_id) as uow:
            catalog_slot = await uow.catalog_image_slots.get(tenant_id, catalog_image_slot_id)
            if catalog_slot is None:
                raise NotFoundError("Catalog image slot not found.")

            asset = await uow.assets.get(tenant_id, source_asset_id)
            if asset is None:
                raise NotFoundError("Source asset not found.")
            if asset.kind != AssetKind.TEMPLATE:
                raise ValidationError("Source asset must be an uploaded template image.")

            existing = await uow.catalog_templates.get_latest_version(
                tenant_id, catalog_image_slot_id, name
            )
            version = existing.version + 1 if existing is not None else 1

            now = self._clock.now()
            template = CatalogTemplate.create_from_upload(
                tenant_id,
                catalog_image_slot_id,
                name=name,
                source_asset_id=source_asset_id,
                created_by=actor_user_id,
                now=now,
                version=version,
            )
            await uow.catalog_templates.add(template)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="catalog_template.created",
                subject_type="catalog_template",
                subject_id=template.id,
                before=None,
                after={
                    "kind": "analysed_image",
                    "status": template.status.value,
                    "version": version,
                },
                now=now,
            )

            return template
