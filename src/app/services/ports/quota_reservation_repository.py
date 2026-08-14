"""Atomic quota reservation (D24) — the guard against a burst of concurrent
requests blowing through a cost budget by an unbounded margin. `reserve()`
is a single conditional `UPDATE`
(`reserved = reserved + n WHERE limit_value - reserved >= n`), never a
read-then-write pair; that is the entire reason this port exists rather
than a plain counter a use case reads and checks itself.

`reserve()` returns `False` both when the row is at capacity **and** when
no row exists for `(tenant_id, period, metric)` at all — a metric nobody
has provisioned a limit for is treated as zero quota available, not
unlimited. Fail closed, not open: silently allowing unmetered spend because
provisioning was forgotten is the worse failure mode.

Not a rich domain object — same "stored counter" shape as
`OutboxEventRepository`/`TaskQueue`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.ids import TenantId


@dataclass(frozen=True)
class QuotaReservation:
    id: UUID
    tenant_id: TenantId
    period: str
    metric: str
    limit_value: int
    reserved: int
    committed: int


class QuotaReservationRepository(Protocol):
    async def ensure_period(
        self, tenant_id: TenantId, *, period: str, metric: str, limit_value: int, now: datetime
    ) -> None:
        """Idempotent: creates the row with this limit if none exists yet.
        Never overwrites an existing row's `limit_value` — raising or
        changing a tenant's limit mid-period is a billing/plan-change
        concern, out of scope for this port."""
        ...

    async def reserve(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> bool:
        """The atomic conditional update. `True` if reserved, `False` if
        the reservation would exceed `limit_value` or nothing was
        provisioned for this `(period, metric)`."""
        ...

    async def commit(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        """Call on success. Bumps the reporting counter `committed`;
        `reserved` is untouched — the quantity was already accounted for
        the moment `reserve()` succeeded."""
        ...

    async def release(
        self, tenant_id: TenantId, *, period: str, metric: str, quantity: int, now: datetime
    ) -> None:
        """Call on terminal failure. Gives the quantity back to `reserved`
        so a failed attempt does not permanently consume budget it never
        used."""
        ...

    async def get(
        self, tenant_id: TenantId, *, period: str, metric: str
    ) -> QuotaReservation | None: ...
