"""Runs against both InMemorySettingsRepository and SqlSettingsRepository.
The real leg seeds a tenant so a tenant-scoped row's plain FK has something
to point at; a platform-scoped row needs no tenant at all.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.setting import Setting, SettingScope
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.settings_repository import SqlSettingsRepository
from app.services.ports.settings_repository import SettingsRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id
from tests.fakes.settings_repository import InMemorySettingsRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    settings: SettingsRepository
    tenant_id: TenantId


async def _make_real_fixture() -> TenantId:
    tenant_id = new_tenant_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemorySettingsRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlSettingsRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_unknown_setting_returns_none(ctx: Context) -> None:
    assert (
        await ctx.settings.get(ctx.tenant_id, SettingScope.TENANT, None, "approval.required")
        is None
    )


async def test_add_then_get_round_trips_a_tenant_scoped_setting(ctx: Context) -> None:
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=ctx.tenant_id,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )

    await ctx.settings.add(setting)

    fetched = await ctx.settings.get(ctx.tenant_id, SettingScope.TENANT, None, "approval.required")
    assert fetched is not None
    assert fetched.value is True


async def test_update_persists_the_mutated_value(ctx: Context) -> None:
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=ctx.tenant_id,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )
    await ctx.settings.add(setting)

    setting.value = False
    await ctx.settings.update(setting)

    fetched = await ctx.settings.get(ctx.tenant_id, SettingScope.TENANT, None, "approval.required")
    assert fetched is not None
    assert fetched.value is False


async def test_a_complex_json_value_round_trips(ctx: Context) -> None:
    value = {"required_channels": ["instagram", "facebook", "pinterest"]}
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=ctx.tenant_id,
        scope_id=None,
        key="approval.required_channels",
        value=value,
        now=utcnow(),
    )

    await ctx.settings.add(setting)

    fetched = await ctx.settings.get(
        ctx.tenant_id, SettingScope.TENANT, None, "approval.required_channels"
    )
    assert fetched is not None
    assert fetched.value == value
