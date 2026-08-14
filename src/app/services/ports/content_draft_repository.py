"""Port for `content_drafts` (D23) — the mutable current-state row per
(variant, channel, locale). `update` exists for the same reason it does on
`CatalogImageRepository`: this row is revised over its lifecycle, and
`mark_superseded` on the *existing* row is one half of the edit/regenerate
transaction (not built yet — see `entities.content_draft`'s docstring).
`get_live` finds that existing row — the one with `superseded_by IS NULL`
for a given (variant, channel, locale), i.e. the row the partial unique
index currently protects.

No `list_page` yet, matching `CatalogImageRepository`'s own history — that
arrived once a real approval-queue caller needed it, not in the storage-only
chunk that first introduced the table.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.content_draft import ContentDraft
from app.shared.ids import ContentDraftId, ProductVariantId, TenantId


class ContentDraftRepository(Protocol):
    async def get(self, tenant_id: TenantId, draft_id: ContentDraftId) -> ContentDraft | None: ...

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, *, channel: str, locale: str
    ) -> ContentDraft | None:
        """The row for this (variant, channel, locale) with
        `superseded_by IS NULL`, if any — at most one can exist, enforced by
        the partial unique index."""
        ...

    async def add(self, draft: ContentDraft) -> None: ...

    async def update(self, draft: ContentDraft) -> None: ...

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[ContentDraft]: ...
