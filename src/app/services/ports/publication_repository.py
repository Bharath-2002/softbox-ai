"""Port for `publications` (D21). `get`/`add`/`update` — the same minimal
shape `GenerationRequestRepository` established, since `update` has a real
caller from this chunk's first commit (unlike `SocialAccountRepository`,
which has none yet).

`get_live` backs `CreatePublication`'s single-flight pre-check: a
publication is "live" while it is `scheduled`, `dispatching` or `failed` —
still in flight, as opposed to `published`/`dead`/`cancelled` where a new
attempt for the same `(channel_id, variant_id)` pair is legitimate. The
migration's partial unique index enforces the same "live" definition as
the backstop for the check-then-act race between two concurrent calls.

`list_due_for_release` backs the `due_at` poller
(`features.publishing.release_scheduled_publications`): every `scheduled`
publication whose `due_at` has passed, locked with `SKIP LOCKED` the same
way `GenerationRequestRepository.list_running_for_update` locks its own
sweep candidates, so two concurrent sweeps for one tenant partition rather
than double-release the same row.

`claim_for_metrics_fetch` backs `StartPublicationMetricsFetch`: the oldest
`published` row whose `metrics_fetched_at` is unset or past `before`,
locked with the same `SKIP LOCKED` shape. A single row, not a batch list —
`fetch_metrics` is an external call, so this claims one at a time the way
`TaskQueue.claim` does, not a batch reconciler sweep like
`list_due_for_release`.
"""

from __future__ import annotations

from datetime import datetime
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

    async def list_due_for_release(
        self, tenant_id: TenantId, *, before: datetime, limit: int
    ) -> list[Publication]: ...

    async def claim_for_metrics_fetch(
        self, tenant_id: TenantId, *, before: datetime
    ) -> Publication | None: ...

    async def add(self, publication: Publication) -> None: ...

    async def update(self, publication: Publication) -> None: ...
