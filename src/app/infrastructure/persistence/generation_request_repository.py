"""Implements
``app.services.ports.generation_request_repository.GenerationRequestRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.generation_request import GenerationRequest
from app.infrastructure.persistence.mapping import generation_requests_table
from app.shared.ids import GenerationRequestId, TenantId


class SqlGenerationRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> GenerationRequest | None:
        stmt = select(GenerationRequest).where(
            generation_requests_table.c.tenant_id == tenant_id,
            generation_requests_table.c.id == request_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, request: GenerationRequest) -> None:
        self._session.add(request)
        await self._session.flush()

    async def update(self, request: GenerationRequest) -> None:
        await self._session.flush()
