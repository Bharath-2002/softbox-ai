"""Port for `publications` (D21). `get`/`add`/`update` — the same minimal
shape `GenerationRequestRepository` established, since `update` has a real
caller from this chunk's first commit (unlike `SocialAccountRepository`,
which has none yet).

`get_live` backs `CreatePublication`'s single-flight pre-check: a
publication is "live" while it is `pending` or `publishing` — still trying,
as opposed to `published`/`failed` where it is done and a new attempt for
the same `(channel_id, variant_id)` pair is legitimate. The migration's
partial unique index enforces the same "live" definition as the backstop
for the check-then-act race between two concurrent calls.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.publication import Publication
from app.shared.ids import ProductVariantId, PublicationId, SocialAccountId, TenantId


class PublicationRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, publication_id: PublicationId
    ) -> Publication | None: ...

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, channel_id: SocialAccountId
    ) -> Publication | None: ...

    async def add(self, publication: Publication) -> None: ...

    async def update(self, publication: Publication) -> None: ...
