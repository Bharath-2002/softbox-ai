"""Port for `generation_items` (D18) — the immutable per-attempt log.
`get`/`add`/`list_for_request` only; same shape as
`GenerationRequestRepository`, no `update` since a row is never revised
after creation in this chunk (see `entities.generation_item`'s module
docstring for why a retry is a new row, not an in-place transition).
"""

from __future__ import annotations

from typing import Protocol

from app.entities.generation_item import GenerationItem
from app.shared.ids import GenerationItemId, GenerationRequestId, TenantId


class GenerationItemRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, item_id: GenerationItemId
    ) -> GenerationItem | None: ...

    async def add(self, item: GenerationItem) -> None: ...

    async def list_for_request(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> list[GenerationItem]: ...
