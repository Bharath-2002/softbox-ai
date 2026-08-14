"""The M5 Gate's hardest-to-retrofit bullet: N parallel `reserve()` calls
against a budget of M < N must reserve **exactly** M, never more (check-
then-act blowing through the budget) and never fewer (the conditional
`UPDATE` deadlocking or under-granting). Reuses the exact `app_uow`/
`asyncio.gather`-over-genuinely-separate-connections fixture shape
``test_task_queue_concurrency.py`` proved out first — same class of
guarantee, same reason a single-session contract test cannot express it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from sqlalchemy import text

from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

UowFactory = Callable[[TenantId | None], SqlUnitOfWork]

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _seed_tenant_with_quota(owner_uow: UowFactory, *, limit_value: int) -> TenantId:
    tenant_id = new_tenant_id()
    now = utcnow()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    async with owner_uow(tenant_id) as uow:
        await uow.quota_reservations.ensure_period(
            tenant_id,
            period="2026-08",
            metric="generation.images",
            limit_value=limit_value,
            now=now,
        )
    return tenant_id


async def test_concurrent_reservations_never_exceed_the_budget(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    """Each claimant opens, reserves, and closes its **own** unit of work
    within one coroutine — unlike ``test_task_queue_concurrency.py``'s
    ``claim()`` (which uses ``SKIP LOCKED`` and never blocks), a plain
    conditional ``UPDATE`` blocks on the row lock. Holding N transactions
    open simultaneously without letting any of them commit would deadlock
    every claimant on the same row forever; committing each as soon as its
    own reservation attempt finishes lets Postgres serialize the row-locked
    updates one at a time while still proving genuine concurrent contention
    (all N attempts are in flight together via ``asyncio.gather``)."""
    budget = 5
    claimants = 10
    tenant_id = await _seed_tenant_with_quota(owner_uow, limit_value=budget)
    now = utcnow()

    async def _attempt() -> bool:
        async with app_uow(tenant_id) as uow:
            return await uow.quota_reservations.reserve(
                tenant_id, period="2026-08", metric="generation.images", quantity=1, now=now
            )

    results = await asyncio.gather(*[_attempt() for _ in range(claimants)])

    assert sum(1 for r in results if r is True) == budget
    assert sum(1 for r in results if r is False) == claimants - budget

    async with owner_uow(tenant_id) as uow:
        row = await uow.quota_reservations.get(
            tenant_id, period="2026-08", metric="generation.images"
        )
    assert row is not None
    assert row.reserved == budget
