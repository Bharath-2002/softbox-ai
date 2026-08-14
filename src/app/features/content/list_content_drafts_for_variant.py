"""Lists a variant's **live** (non-superseded) content drafts — the
smallest useful "what can I approve for this variant" view. Not a
cursor-paginated `list_page` like `ListCatalogImagesForReview` — no
multi-variant approval-queue view exists yet for content drafts, so there
is no caller that needs cross-variant pagination; add one if that changes,
matching `CatalogImageRepository.list_page`'s own history of arriving once
a real caller needed it.
"""

from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import ProductVariantId, TenantId


class ListContentDraftsForVariant:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[ContentDraft]:
        async with self._uow_factory(tenant_id) as uow:
            drafts = await uow.content_drafts.list_for_variant(tenant_id, variant_id)
            return [d for d in drafts if d.superseded_by is None]
