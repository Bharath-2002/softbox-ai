"""Port for `generation_items` (D18) — the immutable per-attempt log.
"Immutable" is about lineage (model, prompt, seed, template), not status:
`update` exists because `mark_running`/`mark_succeeded`/`mark_failed`/
`mark_dead` all revise a row in place (see `entities.generation_item`'s
module docstring for the transient-retry-vs-QC-retry distinction that
makes this correct rather than a contradiction).
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

    async def update(self, item: GenerationItem) -> None: ...

    async def list_for_request(
        self, tenant_id: TenantId, request_id: GenerationRequestId
    ) -> list[GenerationItem]: ...
