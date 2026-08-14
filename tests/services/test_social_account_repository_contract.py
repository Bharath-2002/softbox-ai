"""Runs against both InMemorySocialAccountRepository and
SqlSocialAccountRepository. The real leg only needs a `tenant` row -
`social_accounts.tenant_id` FKs straight to `tenants.id`, unlike
`content_drafts`' longer chain down to a `product_variant`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.social_account import SocialAccount, SocialAccountStatus
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.social_account_repository import SqlSocialAccountRepository
from app.services.ports.social_account_repository import SocialAccountRepository
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_social_account_id, new_tenant_id
from tests.fakes.social_account_repository import InMemorySocialAccountRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    accounts: SocialAccountRepository
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
        yield Context(InMemorySocialAccountRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlSocialAccountRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _account(ctx: Context, *, external_account_id: str = "ig-123") -> SocialAccount:
    return SocialAccount.create(
        ctx.tenant_id,
        provider="instagram",
        external_account_id=external_account_id,
        display_name="The Saree Studio",
        now=utcnow(),
    )


async def test_unknown_account_returns_none(ctx: Context) -> None:
    assert await ctx.accounts.get(ctx.tenant_id, new_social_account_id()) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    account = _account(ctx)

    await ctx.accounts.add(account)

    fetched = await ctx.accounts.get(ctx.tenant_id, account.id)
    assert fetched is not None
    # Identity, not just `.value` equality - the exact `Role`-mapping
    # degradation `mapping.py`'s own docstring records hitting once.
    assert fetched.status is SocialAccountStatus.CONNECTED
    assert fetched.provider == "instagram"
    assert fetched.external_account_id == "ig-123"
    assert fetched.scopes == []
    assert fetched.credentials_encrypted is None
    assert fetched.encryption_key_id is None
