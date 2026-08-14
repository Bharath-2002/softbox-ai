from __future__ import annotations

from app.entities.generation_request import GenerationRequest, GenerationRequestStatus
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

    async def update(self, request: GenerationRequest) -> None:
        self._rows[(request.tenant_id, request.id)] = request

    async def list_running_for_update(
        self, tenant_id: TenantId, *, limit: int = 50
    ) -> list[GenerationRequest]:
        # SKIP LOCKED concurrency is a real-Postgres-only property — same
        # posture `SqlTaskQueue.claim`'s own fake takes (see
        # `test_task_queue_contract.py`'s module docstring).
        matches = [
            row
            for row in self._rows.values()
            if row.tenant_id == tenant_id and row.status == GenerationRequestStatus.RUNNING
        ]
        matches.sort(key=lambda row: row.created_at)
        return matches[:limit]
