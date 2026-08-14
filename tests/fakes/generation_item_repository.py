from __future__ import annotations

from app.entities.generation_item import GenerationItem
from app.shared.ids import GenerationItemId, GenerationRequestId, TenantId


class InMemoryGenerationItemRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, GenerationItemId], GenerationItem] = {}

    async def get(self, tenant_id: TenantId, item_id: GenerationItemId) -> GenerationItem | None:
        return self._rows.get((tenant_id, item_id))

    async def add(self, item: GenerationItem) -> None:
        self._rows[(item.tenant_id, item.id)] = item

    async def update(self, item: GenerationItem) -> None:
        self._rows[(item.tenant_id, item.id)] = item

    async def list_for_request(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> list[GenerationItem]:
        return [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id and row.request_id == request_id
        ]
