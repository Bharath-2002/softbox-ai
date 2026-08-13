"""``SettingsResolver`` against real Postgres, not the fakes
(``test_settings_resolver.py`` covers resolution logic; this covers
something only the real database can prove).

The resolver issues two separate ``settings.get`` calls inside one bound
session — one for a platform row (``tenant_id IS NULL``), one for a tenant
row (``tenant_id = bound``) — relying on the same RLS policy to permit both
reads under a single ``app.current_tenant`` binding (the migration's
``USING (tenant_id IS NULL OR tenant_id = bound)`` clause). Nothing else in
the suite proves that combination actually works against the real policy
rather than against the fake, which has no RLS to get wrong.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text

from app.entities.category import Category
from app.entities.setting import Setting, SettingScope
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.services.settings_resolver import SettingsResolver
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


async def test_resolve_reads_the_platform_default_and_the_tenant_override_in_one_bound_session(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = new_tenant_id()
    key = f"approval.required.{uuid.uuid4()}"
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )

    async with app_uow(None) as uow:
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.PLATFORM,
                tenant_id=None,
                scope_id=None,
                key=key,
                value=False,
                now=utcnow(),
            )
        )
    async with app_uow(tenant_id) as uow:
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.TENANT,
                tenant_id=tenant_id,
                scope_id=None,
                key=key,
                value=True,
                now=utcnow(),
            )
        )

    async with app_uow(tenant_id) as uow:
        resolver = SettingsResolver(uow.settings, uow.categories)
        resolved = await resolver.resolve(tenant_id, key)

    assert resolved is True


async def test_resolve_falls_back_to_the_platform_default_when_no_tenant_override_exists(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = new_tenant_id()
    key = f"qc.min_confidence.{uuid.uuid4()}"
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
    async with app_uow(None) as uow:
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.PLATFORM,
                tenant_id=None,
                scope_id=None,
                key=key,
                value=0.7,
                now=utcnow(),
            )
        )

    async with app_uow(tenant_id) as uow:
        resolver = SettingsResolver(uow.settings, uow.categories)
        resolved = await resolver.resolve(tenant_id, key)

    assert resolved == 0.7


async def test_resolve_walks_the_category_chain_in_one_bound_session(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
    app_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = new_tenant_id()
    key = f"approval.required.{uuid.uuid4()}"
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )

    now = utcnow()
    root = Category.create(
        tenant_id,
        key="apparel",
        name="Apparel",
        slug=f"apparel-{uuid.uuid4()}",
        parent=None,
        now=now,
    )
    leaf = Category.create(
        tenant_id, key="sarees", name="Sarees", slug=f"sarees-{uuid.uuid4()}", parent=root, now=now
    )
    async with app_uow(tenant_id) as uow:
        await uow.categories.add(root)
        await uow.categories.add(leaf)
        await uow.settings.add(
            Setting.create(
                scope_type=SettingScope.CATEGORY,
                tenant_id=tenant_id,
                scope_id=leaf.id,
                key=key,
                value=True,
                now=now,
            )
        )

    async with app_uow(tenant_id) as uow:
        resolver = SettingsResolver(uow.settings, uow.categories)
        resolved = await resolver.resolve(tenant_id, key, category_id=leaf.id)

    assert resolved is True
