"""Port for `publications` (D21). `get`/`add`/`update` — the same minimal
shape `GenerationRequestRepository` established, since `update` has a real
caller from this chunk's first commit (unlike `SocialAccountRepository`,
which has none yet).
"""

from __future__ import annotations

from typing import Protocol

from app.entities.publication import Publication
from app.shared.ids import PublicationId, TenantId


class PublicationRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, publication_id: PublicationId
    ) -> Publication | None: ...

    async def add(self, publication: Publication) -> None: ...

    async def update(self, publication: Publication) -> None: ...
