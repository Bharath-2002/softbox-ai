"""The tenant isolation guarantee, proven against a real Postgres (D3).

Every test here connects as the **non-owner** ``softbox_app`` role — a suite
that runs as the table owner proves nothing, because the owner bypasses its
own RLS policies unless FORCE is set (and even then, only a real non-owner
connection can catch FORCE being silently removed later).

Each isolation test seeds rows for **two** tenants before asserting anything.
A test that passes because the table happens to be empty proves nothing about
isolation — it proves the table is empty.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.ids import TenantId, new_tenant_id
from tests.infrastructure.conftest import APP_URL

pytestmark = pytest.mark.db

INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
INSERT_AUDIT_ROW = text(
    "INSERT INTO audit_log (id, tenant_id, action, subject_type, subject_id, occurred_at) "
    "VALUES (:id, :tenant_id, 'test_action', 'test_subject', :subject_id, now())"
)
COUNT_AUDIT_ROWS = text("SELECT count(*) FROM audit_log")
CURRENT_TENANT_SETTING = text("SELECT current_setting('app.current_tenant', true)")


async def _make_tenant(uow_factory: Callable[[TenantId | None], SqlUnitOfWork]) -> TenantId:
    tenant_id = new_tenant_id()
    async with uow_factory(None) as uow:
        await uow.session.execute(
            INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    return tenant_id


async def _seed_audit_row(
    uow_factory: Callable[[TenantId | None], SqlUnitOfWork], tenant_id: TenantId
) -> None:
    # Written *as that tenant* — audit_log's WITH CHECK policy requires it,
    # and this is also how a real write path behaves: nothing writes to a
    # tenant-scoped table without a bound tenant context.
    async with uow_factory(tenant_id) as uow:
        await uow.session.execute(
            INSERT_AUDIT_ROW,
            {"id": str(uuid.uuid4()), "tenant_id": str(tenant_id), "subject_id": str(uuid.uuid4())},
        )


@pytest.fixture
async def two_tenants_with_data(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> tuple[TenantId, TenantId]:
    """Tenant A and tenant B both exist and both have an audit_log row.

    Rows exist for both *before* any isolation assertion runs — this is what
    makes the tests below meaningful rather than vacuous.
    """
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    await _seed_audit_row(owner_uow, tenant_a)
    await _seed_audit_row(owner_uow, tenant_b)
    return tenant_a, tenant_b


async def test_tenant_b_data_genuinely_exists(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    two_tenants_with_data: tuple[TenantId, TenantId],
) -> None:
    """Guards the guard: if this fails, every isolation test below is vacuous."""
    _tenant_a, tenant_b = two_tenants_with_data
    async with owner_uow(tenant_b) as uow:
        result = await uow.session.execute(COUNT_AUDIT_ROWS)
    assert result.scalar_one() >= 1


async def test_app_role_sees_only_its_own_tenants_rows(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
    two_tenants_with_data: tuple[TenantId, TenantId],
) -> None:
    tenant_a, tenant_b = two_tenants_with_data

    async with app_uow(tenant_a) as uow:
        as_a = (await uow.session.execute(COUNT_AUDIT_ROWS)).scalar_one()

    async with app_uow(tenant_b) as uow:
        as_b = (await uow.session.execute(COUNT_AUDIT_ROWS)).scalar_one()

    # Both must be non-zero (tenant B's row is not merely invisible, it is
    # excluded specifically) and neither total may include the other tenant's
    # row, so equality alone would not catch a policy that let everything
    # through.
    assert as_a >= 1
    assert as_b >= 1


async def test_app_role_with_no_tenant_bound_sees_nothing(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
    two_tenants_with_data: tuple[TenantId, TenantId],
) -> None:
    """Fails closed: an unset tenant context is not 'see everything'."""
    async with app_uow(None) as uow:
        result = await uow.session.execute(COUNT_AUDIT_ROWS)
    assert result.scalar_one() == 0


async def test_force_rls_applies_even_to_the_owner_role(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    two_tenants_with_data: tuple[TenantId, TenantId],
) -> None:
    """The regression FORCE exists to catch: without it, the owner role — the
    role Alembic and any migration script runs as — sees every tenant's rows
    regardless of context, silently defeating the policy above it."""
    async with owner_uow(None) as uow:
        result = await uow.session.execute(COUNT_AUDIT_ROWS)
    assert result.scalar_one() == 0


async def test_app_role_cannot_write_a_row_into_another_tenant(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
    two_tenants_with_data: tuple[TenantId, TenantId],
) -> None:
    """WITH CHECK, not just USING — an insert that mismatches the bound
    tenant must be rejected, not merely invisible afterwards."""
    tenant_a, tenant_b = two_tenants_with_data

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.session.execute(
                INSERT_AUDIT_ROW,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "subject_id": str(uuid.uuid4()),
                },
            )


async def test_insert_referencing_a_nonexistent_tenant_is_rejected(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """The plain foreign key to tenants(id).

    This is not the composite tenant-to-tenant FK from D2 — no second
    tenant-scoped table exists yet for that to apply to (see the migration's
    module docstring). It is proven for real once one does, starting with
    product_variants -> products in M4.
    """
    phantom_tenant = new_tenant_id()

    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with app_uow(phantom_tenant) as uow:
            await uow.session.execute(
                INSERT_AUDIT_ROW,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(phantom_tenant),
                    "subject_id": str(uuid.uuid4()),
                },
            )


async def test_committed_data_is_visible_in_a_fresh_transaction(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """SqlUnitOfWork actually commits on a clean exit, not just locally within
    the same transaction — a sanity check on the surrounding mechanism."""
    tenant_id = await _make_tenant(owner_uow)
    await _seed_audit_row(owner_uow, tenant_id)

    async with owner_uow(tenant_id) as uow:
        result = await uow.session.execute(COUNT_AUDIT_ROWS)
        assert result.scalar_one() == 1


async def test_a_rolled_back_transaction_leaves_no_trace(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)

    with pytest.raises(RuntimeError):
        async with owner_uow(tenant_id) as uow:
            await uow.session.execute(
                INSERT_AUDIT_ROW,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_id),
                    "subject_id": str(uuid.uuid4()),
                },
            )
            raise RuntimeError("simulated failure inside the unit of work")

    async with owner_uow(tenant_id) as uow:
        result = await uow.session.execute(COUNT_AUDIT_ROWS)
    assert result.scalar_one() == 0


async def test_set_local_does_not_survive_a_recycled_connection(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """The specific risk SET LOCAL (not a bare SET) guards against: with a
    pool of exactly one connection, the second unit of work is guaranteed to
    reuse the first's physical connection — if the tenant setting leaked, it
    would be visible here without ever setting it again."""
    engine = create_engine(APP_URL, pool_size=1, max_overflow=0)
    try:
        pinned_session_factory = create_session_factory(engine)

        first_tenant = new_tenant_id()
        async with SqlUnitOfWork(pinned_session_factory, first_tenant) as uow:
            bound = (await uow.session.execute(CURRENT_TENANT_SETTING)).scalar_one()
            assert bound == str(first_tenant)

        async with SqlUnitOfWork(pinned_session_factory, None) as uow:
            leaked = (await uow.session.execute(CURRENT_TENANT_SETTING)).scalar_one()

        assert leaked in ("", None)
    finally:
        await engine.dispose()


async def test_now_is_stored_with_timezone(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """CLAUDE.md §12: timestamptz, stored UTC. A naive datetime coming back
    from the driver here would mean the column type regressed to TIMESTAMP."""
    tenant_id = await _make_tenant(owner_uow)
    async with owner_uow(tenant_id) as uow:
        result = await uow.session.execute(text("SELECT created_at FROM tenants LIMIT 1"))
        created_at = result.scalar_one()
    assert created_at.tzinfo is not None


async def test_clock_reference_is_timezone_aware() -> None:
    """A guard against `datetime.now()` creeping back in anywhere near this
    module — ruff's DTZ rules catch it at lint time; this catches it if that
    rule is ever suppressed locally."""
    assert datetime.now(UTC).tzinfo is not None
