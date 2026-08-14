"""Port for `generation_requests` (D18). `update` exists alongside
`get`/`add` now that `FanOutGenerationItems` drives the first real status
transition (`mark_running`) — the same "add the mutation exactly when a
real caller needs it" discipline `CatalogImageRepository` followed.

`list_running_for_update` is the reconciler's discovery query
(`features.generation.reconcile_generation_requests_for_tenant`) — locked
with `SKIP LOCKED`, the same primitive `TaskQueue.claim` uses, so two
concurrent reconcile sweeps for the same tenant partition the running
requests between them instead of double-settling one and double-counting
its quota commit/release. Unlike `TaskQueue.claim` this returns a batch,
not a single row, because reconciliation is a bounded sweep over "whatever
is ready to settle right now," not a one-job-at-a-time work queue.
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

    async def list_running_for_update(
        self, tenant_id: TenantId, *, limit: int = 50
    ) -> list[GenerationRequest]: ...
