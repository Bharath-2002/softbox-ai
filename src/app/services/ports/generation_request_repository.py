"""Port for `generation_requests` (D18). `update` exists alongside
`get`/`add` now that `FanOutGenerationItems` drives the first real status
transition (`mark_running`) — the same "add the mutation exactly when a
real caller needs it" discipline `CatalogImageRepository` followed.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.generation_request import GenerationRequest
from app.shared.ids import GenerationRequestId, TenantId


class GenerationRequestRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> GenerationRequest | None: ...

    async def add(self, request: GenerationRequest) -> None: ...

    async def update(self, request: GenerationRequest) -> None: ...
