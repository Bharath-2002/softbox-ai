from __future__ import annotations

import uuid

import pytest

from app.entities.setting import Setting, SettingScope
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_category_id, new_tenant_id


def test_platform_scope_requires_no_tenant_or_scope_id() -> None:
    setting = Setting.create(
        scope_type=SettingScope.PLATFORM,
        tenant_id=None,
        scope_id=None,
        key="approval.required",
        value=True,
        now=utcnow(),
    )

    assert setting.tenant_id is None
    assert setting.scope_id is None


def test_platform_scope_rejects_a_tenant_id() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.PLATFORM,
            tenant_id=new_tenant_id(),
            scope_id=None,
            key="approval.required",
            value=True,
            now=utcnow(),
        )


def test_tenant_scope_requires_a_tenant_and_no_scope_id() -> None:
    tenant_id = new_tenant_id()
    setting = Setting.create(
        scope_type=SettingScope.TENANT,
        tenant_id=tenant_id,
        scope_id=None,
        key="approval.required",
        value=False,
        now=utcnow(),
    )

    assert setting.tenant_id == tenant_id
    assert setting.scope_id is None


def test_tenant_scope_rejects_a_scope_id() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=new_tenant_id(),
            scope_id=uuid.uuid4(),
            key="approval.required",
            value=False,
            now=utcnow(),
        )


def test_tenant_scope_rejects_a_missing_tenant() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=None,
            scope_id=None,
            key="approval.required",
            value=False,
            now=utcnow(),
        )


def test_category_scope_requires_both_tenant_and_scope_id() -> None:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    setting = Setting.create(
        scope_type=SettingScope.CATEGORY,
        tenant_id=tenant_id,
        scope_id=category_id,
        key="approval.required",
        value=True,
        now=utcnow(),
    )

    assert setting.scope_id == category_id


def test_category_scope_rejects_a_missing_scope_id() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=new_tenant_id(),
            scope_id=None,
            key="approval.required",
            value=True,
            now=utcnow(),
        )


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.PLATFORM,
            tenant_id=None,
            scope_id=None,
            key="",
            value=True,
            now=utcnow(),
        )


def test_key_with_surrounding_whitespace_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Setting.create(
            scope_type=SettingScope.PLATFORM,
            tenant_id=None,
            scope_id=None,
            key=" approval.required ",
            value=True,
            now=utcnow(),
        )
