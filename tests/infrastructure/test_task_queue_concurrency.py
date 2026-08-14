"""The property `test_task_queue_contract.py` cannot express: two genuinely
concurrent claimers never get the same job. `SqlTaskQueue.claim` locks and
updates in one statement (`FOR UPDATE SKIP LOCKED`) specifically so this
holds under real concurrent connections, not just a single session's
sequential calls — the same class of guarantee D24's quota-reservation Gate
test needs, proven here first since the queue lands before quota does.
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


async def _seed_tenant(owner_uow: UowFactory) -> TenantId:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    return tenant_id


async def test_two_concurrent_claimers_never_get_the_same_job(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id = await _seed_tenant(owner_uow)
    now = utcnow()
    async with owner_uow(tenant_id) as uow:
        first_job_id = await uow.task_queue.enqueue(
            tenant_id, job_type="test.job", payload={}, run_at=now, now=now
        )
        second_job_id = await uow.task_queue.enqueue(
            tenant_id, job_type="test.job", payload={}, run_at=now, now=now
        )

    uow_a = app_uow(tenant_id)
    uow_b = app_uow(tenant_id)
    await uow_a.__aenter__()
    await uow_b.__aenter__()
    try:
        claimed_a, claimed_b = await asyncio.gather(
            uow_a.task_queue.claim(tenant_id, claimed_by="worker-a", now=now),
            uow_b.task_queue.claim(tenant_id, claimed_by="worker-b", now=now),
        )
    finally:
        await uow_a.__aexit__(None, None, None)
        await uow_b.__aexit__(None, None, None)

    assert claimed_a is not None
    assert claimed_b is not None
    assert claimed_a.id != claimed_b.id
    assert {claimed_a.id, claimed_b.id} == {first_job_id, second_job_id}


async def test_two_concurrent_claimers_with_only_one_job_never_both_succeed(
    owner_uow: UowFactory, app_uow: UowFactory
) -> None:
    tenant_id = await _seed_tenant(owner_uow)
    now = utcnow()
    async with owner_uow(tenant_id) as uow:
        job_id = await uow.task_queue.enqueue(
            tenant_id, job_type="test.job", payload={}, run_at=now, now=now
        )

    uow_a = app_uow(tenant_id)
    uow_b = app_uow(tenant_id)
    await uow_a.__aenter__()
    await uow_b.__aenter__()
    try:
        claimed_a, claimed_b = await asyncio.gather(
            uow_a.task_queue.claim(tenant_id, claimed_by="worker-a", now=now),
            uow_b.task_queue.claim(tenant_id, claimed_by="worker-b", now=now),
        )
    finally:
        await uow_a.__aexit__(None, None, None)
        await uow_b.__aexit__(None, None, None)

    winners = [c for c in (claimed_a, claimed_b) if c is not None]
    losers = [c for c in (claimed_a, claimed_b) if c is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0].id == job_id
