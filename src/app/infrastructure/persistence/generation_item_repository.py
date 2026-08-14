"""Implements
``app.services.ports.generation_item_repository.GenerationItemRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.generation_item import GenerationItem
from app.infrastructure.persistence.mapping import generation_items_table
from app.shared.ids import GenerationItemId, GenerationRequestId, TenantId


class SqlGenerationItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, item_id: GenerationItemId) -> GenerationItem | None:
        stmt = select(GenerationItem).where(
            generation_items_table.c.tenant_id == tenant_id,
            generation_items_table.c.id == item_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, item: GenerationItem) -> None:
        self._session.add(item)
        await self._session.flush()

    async def update(self, item: GenerationItem) -> None:
        await self._session.flush()

    async def list_for_request(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> list[GenerationItem]:
        stmt = select(GenerationItem).where(
            generation_items_table.c.tenant_id == tenant_id,
            generation_items_table.c.request_id == request_id,
        )
        return list((await self._session.execute(stmt)).scalars().all())
