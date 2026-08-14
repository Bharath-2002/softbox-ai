from __future__ import annotations

from app.entities.content_draft import ContentDraft
from app.shared.ids import ContentDraftId, ProductVariantId, TenantId


class InMemoryContentDraftRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, ContentDraftId], ContentDraft] = {}

    async def get(self, tenant_id: TenantId, draft_id: ContentDraftId) -> ContentDraft | None:
        return self._rows.get((tenant_id, draft_id))

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, *, channel: str, locale: str
    ) -> ContentDraft | None:
        for (tid, _), row in self._rows.items():
            if (
                tid == tenant_id
                and row.variant_id == variant_id
                and row.channel == channel
                and row.locale == locale
                and row.superseded_by is None
            ):
                return row
        return None

    async def add(self, draft: ContentDraft) -> None:
        self._rows[(draft.tenant_id, draft.id)] = draft

    async def update(self, draft: ContentDraft) -> None:
        self._rows[(draft.tenant_id, draft.id)] = draft

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[ContentDraft]:
        return [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.variant_id == variant_id
        ]
