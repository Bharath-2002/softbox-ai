"""Implements
``app.services.ports.content_draft_repository.ContentDraftRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.content_draft import ContentDraft
from app.infrastructure.persistence.mapping import content_drafts_table
from app.shared.ids import ContentDraftId, ProductVariantId, TenantId


class SqlContentDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, draft_id: ContentDraftId) -> ContentDraft | None:
        stmt = select(ContentDraft).where(
            content_drafts_table.c.tenant_id == tenant_id,
            content_drafts_table.c.id == draft_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, *, channel: str, locale: str
    ) -> ContentDraft | None:
        stmt = select(ContentDraft).where(
            content_drafts_table.c.tenant_id == tenant_id,
            content_drafts_table.c.variant_id == variant_id,
            content_drafts_table.c.channel == channel,
            content_drafts_table.c.locale == locale,
            content_drafts_table.c.superseded_by.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, draft: ContentDraft) -> None:
        self._session.add(draft)
        await self._session.flush()

    async def update(self, draft: ContentDraft) -> None:
        await self._session.flush()

    async def list_for_variant(
        self, tenant_id: TenantId, variant_id: ProductVariantId
    ) -> list[ContentDraft]:
        stmt = select(ContentDraft).where(
            content_drafts_table.c.tenant_id == tenant_id,
            content_drafts_table.c.variant_id == variant_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
