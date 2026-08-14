from __future__ import annotations

from app.entities.generation_request import GenerationRequest
from app.shared.ids import GenerationRequestId, TenantId


class InMemoryGenerationRequestRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, GenerationRequestId], GenerationRequest] = {}

    async def get(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> GenerationRequest | None:
        return self._rows.get((tenant_id, request_id))

    async def add(self, request: GenerationRequest) -> None:
        self._rows[(request.tenant_id, request.id)] = request
