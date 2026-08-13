"""Tenant isolation for ``settings`` (D16) — a dual-mode RLS policy, unlike
every other table in this schema: platform-wide rows (``tenant_id IS
NULL``) must be readable by *every* tenant as the resolution fallback, but
writable only by a platform-plane session with no tenant bound at all.
Proven through the real ``UnitOfWork`` property, same pattern as the other
isolation suites.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.setting import Setting, SettingScope
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def _make_tenant(owner_uow: Callable[[TenantId | None], SqlUnitOfWork]) -> TenantId:
    tenant_id = new_tenant_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    return tenant_id


async def test_tenant_a_cannot_read_tenant_bs_settings(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=tenant_b,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )
    async with app_uow(tenant_b) as uow:
        await uow.settings.add(setting)

    async with app_uow(tenant_a) as uow:
        fetched = await uow.settings.get(tenant_b, SettingScope.TENANT, None, "approval.required")

    assert fetched is None


async def test_every_tenant_can_read_a_platform_wide_setting(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = await _make_tenant(owner_uow)
    # Platform-scoped keys have no tenant to partition them apart, and
    # owner_uow/app_uow commit for real with no rollback (CLAUDE.md §10) - a
    # literal key here would collide with itself on the suite's second run.
    key = f"approval.required.{uuid.uuid4()}"
    async with app_uow(None) as uow:
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.PLATFORM,
                tenant_id=None,
                scope_id=None,
                key=key,
                value=True,
                now=utcnow(),
            )
        )

    async with app_uow(tenant_id) as uow:
        fetched = await uow.settings.get(None, SettingScope.PLATFORM, None, key)

    assert fetched is not None
    assert fetched.value is True


async def test_a_tenant_bound_session_cannot_write_a_platform_wide_row(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = new_tenant_id()
    rogue = Setting.create(
        scope_type=SettingScope.PLATFORM,
        tenant_id=None,
        scope_id=None,
        key=f"approval.required.{uuid.uuid4()}",
        value=True,
        now=utcnow(),
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_id) as uow:
            await uow.settings.add(rogue)


async def test_a_tenant_bound_session_cannot_write_another_tenants_row(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_a = await _make_tenant(owner_uow)
    tenant_b = await _make_tenant(owner_uow)
    rogue = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=tenant_b,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_uow(tenant_a) as uow:
            await uow.settings.add(rogue)


async def test_a_platform_plane_session_can_write_a_platform_wide_row(
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    key = f"qc.min_confidence.{uuid.uuid4()}"
    async with app_uow(None) as uow:
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.PLATFORM,
                tenant_id=None,
                scope_id=None,
                key=key,
                value=0.8,
                now=utcnow(),
            )
        )
        fetched = await uow.settings.get(None, SettingScope.PLATFORM, None, key)

    assert fetched is not None
    assert fetched.value == 0.8


async def test_force_rls_hides_a_tenant_scoped_row_from_the_owner_role_with_no_tenant_bound(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    """Unlike the other isolation suites, asserting the whole table is empty
    would not prove anything here — platform-wide rows are deliberately
    visible with no tenant bound. Filtering to this one tenant-scoped row's
    own id is what isolates FORCE RLS's effect from that legitimate
    always-visible case."""
    tenant_id = await _make_tenant(owner_uow)
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=tenant_id,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )
    async with app_uow(tenant_id) as uow:
        await uow.settings.add(setting)

    async with owner_uow(None) as uow:
        result = await uow.session.execute(
            text("SELECT count(*) FROM settings WHERE id = :id"), {"id": str(setting.id)}
        )

    assert result.scalar_one() == 0
