"""Implements ``app.services.ports.publication_repository.PublicationRepository``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.publication import Publication, PublicationStatus
from app.infrastructure.persistence.mapping import publications_table
from app.shared.ids import ProductVariantId, PublicationId, SocialAccountId, TenantId

_LIVE_STATUSES = (PublicationStatus.PENDING, PublicationStatus.PUBLISHING)


class SqlPublicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, publication_id: PublicationId) -> Publication | None:
        stmt = select(Publication).where(
            publications_table.c.tenant_id == tenant_id,
            publications_table.c.id == publication_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, channel_id: SocialAccountId
    ) -> Publication | None:
        stmt = select(Publication).where(
            publications_table.c.tenant_id == tenant_id,
            publications_table.c.variant_id == variant_id,
            publications_table.c.channel_id == channel_id,
            publications_table.c.status.in_(_LIVE_STATUSES),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, publication: Publication) -> None:
        self._session.add(publication)
        await self._session.flush()

    async def update(self, publication: Publication) -> None:
        await self._session.flush()
