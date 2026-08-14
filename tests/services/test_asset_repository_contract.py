"""Runs against both InMemoryAssetRepository and SqlAssetRepository. Same
shape as ``test_input_image_slot_repository_contract.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.asset import Asset, AssetKind
from app.infrastructure.persistence.asset_repository import SqlAssetRepository
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.asset_repository import AssetRepository
from app.shared.clock import utcnow
from app.shared.ids import AssetId, TenantId, new_asset_id, new_tenant_id
from tests.fakes.asset_repository import InMemoryAssetRepository
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)


@dataclass
class Context:
    assets: AssetRepository
    tenant_id: TenantId


async def _make_real_tenant() -> TenantId:
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
        yield Context(InMemoryAssetRepository(), new_tenant_id())
        return

    tenant_id = await _make_real_tenant()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(SqlAssetRepository(session), tenant_id)
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _asset(
    ctx: Context,
    *,
    sha256: str | None = None,
    kind: AssetKind = AssetKind.INPUT,
) -> Asset:
    return Asset.create(
        ctx.tenant_id,
        storage_key=f"tenants/{ctx.tenant_id}/{new_asset_id()}.jpg",
        sha256=sha256 or ("a" * 64),
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=kind,
        source="upload",
        now=utcnow(),
    )


async def test_unknown_asset_returns_none(ctx: Context) -> None:
    unknown_id = AssetId(new_asset_id())
    assert await ctx.assets.get(ctx.tenant_id, unknown_id) is None


async def test_add_then_get_round_trips(ctx: Context) -> None:
    asset = _asset(ctx)

    await ctx.assets.add(asset)

    fetched = await ctx.assets.get(ctx.tenant_id, asset.id)
    assert fetched is not None
    assert fetched.sha256 == "a" * 64
    assert fetched.mime == "image/jpeg"


async def test_get_by_sha256_finds_a_match_for_the_same_kind(ctx: Context) -> None:
    asset = _asset(ctx, sha256="b" * 64, kind=AssetKind.TEMPLATE)
    await ctx.assets.add(asset)

    found = await ctx.assets.get_by_sha256(ctx.tenant_id, "B" * 64, AssetKind.TEMPLATE)

    assert found is not None
    assert found.id == asset.id


async def test_get_by_sha256_does_not_cross_kind_boundaries(ctx: Context) -> None:
    asset = _asset(ctx, sha256="c" * 64, kind=AssetKind.TEMPLATE)
    await ctx.assets.add(asset)

    found = await ctx.assets.get_by_sha256(ctx.tenant_id, "c" * 64, AssetKind.INPUT)

    assert found is None
