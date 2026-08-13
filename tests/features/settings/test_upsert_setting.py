"""UpsertSetting — creates a row on first write, replaces the value in
place on a second write for the same scope tuple, rather than creating a
duplicate (D16).
"""

from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.setting import SettingScope
from app.features.settings.upsert_setting import UpsertSetting
from app.shared.ids import new_tenant_id


def _use_case() -> tuple[UpsertSetting, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return UpsertSetting(uow_factory, clock), clock, uow_factory


async def test_first_write_creates_a_row() -> None:
    use_case, _clock, uow_factory = _use_case()

    setting = await use_case(
        tenant_id=None,
        scope_type=SettingScope.PLATFORM,
        scope_id=None,
        key="approval.required",
        value=True,
    )

    fetched = await uow_factory.settings.get(None, SettingScope.PLATFORM, None, "approval.required")
    assert fetched is not None
    assert fetched.id == setting.id
    assert fetched.value is True


async def test_second_write_for_the_same_scope_replaces_the_value_in_place() -> None:
    use_case, _clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    first = await use_case(
        tenant_id=tenant_id,
        scope_type=SettingScope.TENANT,
        scope_id=None,
        key="approval.required",
        value=True,
    )

    second = await use_case(
        tenant_id=tenant_id,
        scope_type=SettingScope.TENANT,
        scope_id=None,
        key="approval.required",
        value=False,
    )

    assert second.id == first.id
    fetched = await uow_factory.settings.get(
        tenant_id, SettingScope.TENANT, None, "approval.required"
    )
    assert fetched is not None
    assert fetched.value is False
