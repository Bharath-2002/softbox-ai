"""Port for `generation_requests` (D18). `get`/`add` only, matching
`ProductInputImageRepository`'s shape — the transitions that would justify
an `update` beyond a plain flush land with the worker/reconciler chunks
that actually drive them.
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
