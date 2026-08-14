from __future__ import annotations

from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.setting import Setting, SettingScope
from app.features.settings.resolve_setting import ResolveSetting
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id


async def test_resolves_a_tenant_level_setting() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = ResolveSetting(uow_factory)
    tenant_id = new_tenant_id()
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=tenant_id,
            scope_id=None,
            key="approval.required",
            value=True,
            now=utcnow(),
        )
    )

    resolved = await use_case(tenant_id=tenant_id, key="approval.required")

    assert resolved is True


async def test_unset_key_resolves_to_none() -> None:
    use_case = ResolveSetting(FakeUnitOfWorkFactory())

    resolved = await use_case(tenant_id=new_tenant_id(), key="approval.required")

    assert resolved is None
