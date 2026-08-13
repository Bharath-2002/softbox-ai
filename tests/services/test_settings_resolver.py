"""SettingsResolver against the in-memory fakes — platform -> tenant ->
category (root to leaf), most specific wins (D16).
"""

from __future__ import annotations

import pytest

from app.entities.category import Category
from app.entities.setting import Setting, SettingScope
from app.services.settings_resolver import SettingsResolver
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id
from tests.fakes.category_repository import InMemoryCategoryRepository
from tests.fakes.settings_repository import InMemorySettingsRepository


def _resolver() -> tuple[SettingsResolver, InMemorySettingsRepository, InMemoryCategoryRepository]:
    settings = InMemorySettingsRepository()
    categories = InMemoryCategoryRepository()
    return SettingsResolver(settings, categories), settings, categories


async def test_unset_key_resolves_to_none() -> None:
    resolver, _settings, _categories = _resolver()

    assert await resolver.resolve(new_tenant_id(), "approval.required") is None


async def test_platform_default_is_used_when_nothing_more_specific_is_set() -> None:
    resolver, settings, _categories = _resolver()
    tenant_id = new_tenant_id()
    await settings.add(
        Setting.create(
            scope_type=SettingScope.PLATFORM,
            tenant_id=None,
            scope_id=None,
            key="approval.required",
            value=True,
            now=utcnow(),
        )
    )

    assert await resolver.resolve(tenant_id, "approval.required") is True


async def test_tenant_override_beats_the_platform_default() -> None:
    resolver, settings, _categories = _resolver()
    tenant_id = new_tenant_id()
    await settings.add(
        Setting.create(
            scope_type=SettingScope.PLATFORM,
            tenant_id=None,
            scope_id=None,
            key="approval.required",
            value=True,
            now=utcnow(),
        )
    )
    await settings.add(
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=tenant_id,
            scope_id=None,
            key="approval.required",
            value=False,
            now=utcnow(),
        )
    )

    assert await resolver.resolve(tenant_id, "approval.required") is False


async def test_a_leaf_categorys_override_beats_its_ancestors_and_the_tenant() -> None:
    resolver, settings, categories = _resolver()
    tenant_id = new_tenant_id()
    now = utcnow()
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=now
    )
    leaf = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=root, now=now
    )
    await categories.add(root)
    await categories.add(leaf)

    await settings.add(
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=tenant_id,
            scope_id=None,
            key="approval.required",
            value=True,
            now=now,
        )
    )
    await settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=root.id,
            key="approval.required",
            value=False,
            now=now,
        )
    )
    await settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=leaf.id,
            key="approval.required",
            value=True,
            now=now,
        )
    )

    assert await resolver.resolve(tenant_id, "approval.required", category_id=leaf.id) is True
    # The root's own override still beats the tenant default when resolving
    # for the root itself (no leaf override in scope).
    assert await resolver.resolve(tenant_id, "approval.required", category_id=root.id) is False


async def test_unknown_category_is_not_found() -> None:
    resolver, _settings, _categories = _resolver()

    with pytest.raises(NotFoundError):
        await resolver.resolve(new_tenant_id(), "approval.required", category_id=new_category_id())
