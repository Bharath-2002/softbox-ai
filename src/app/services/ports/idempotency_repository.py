"""Idempotency-key storage for mutating requests that cost money or publish
(CLAUDE.md §6, §9).

A record is written in two steps, not one: ``reserve`` atomically claims the
key before the guarded work runs, and ``store_response`` fills in the
outcome afterward. The gap between them is a legitimate, distinguishable
state — a request that crashed mid-flight leaves a reserved-but-unanswered
row (``response_status is None``), which differs both from "never
attempted" (no row at all) and "already answered" (a status is present). A
single combined write could not represent the in-flight case.

A replay must be checked against the fingerprint of the *original* request,
not just the key's existence — the same key reused with a different body is
a caller bug or a collision, not a legitimate retry, and must be rejected
rather than silently served the first response. Comparing fingerprints is
the caller's job (this port only stores and returns one); see
``IdempotencyRecord.request_fingerprint``.

No route calls this yet (M1 chunk 5) — the mechanism and its tests exist
ahead of the first mutating endpoint that costs money or publishes, per
CLAUDE.md's own rule that idempotency is required for exactly that class of
route. Wiring a use case to call it, inside that use case's own
``UnitOfWork`` transaction, lands together with that first route.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.shared.ids import TenantId


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    request_fingerprint: str
    response_status: int | None
    response_body: dict[str, Any] | None
    created_at: datetime


class IdempotencyRepository(Protocol):
    async def get(self, tenant_id: TenantId, key: str) -> IdempotencyRecord | None: ...

    async def reserve(
        self, tenant_id: TenantId, key: str, *, request_fingerprint: str, now: datetime
    ) -> bool:
        """Atomically claims ``key`` for this tenant.

        Returns ``True`` if this call claimed it — the caller should proceed
        with the guarded work. Returns ``False`` if a record already existed
        (concurrently reserved, or a prior attempt) — the caller must then
        call ``get`` and compare fingerprints rather than proceeding.
        """
        ...

    async def store_response(
        self, tenant_id: TenantId, key: str, *, status: int, body: dict[str, Any] | None
    ) -> None: ...
