from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.asset import Asset, AssetKind
from app.features.assets.request_download import RequestDownload
from app.shared.errors import NotFoundError
from app.shared.ids import new_asset_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[RequestDownload, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return RequestDownload(uow_factory, InMemoryObjectStorage(), FakeClock(_NOW)), uow_factory


async def test_requesting_a_download_returns_a_presigned_get_url() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/input/a.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=100,
        height=100,
        bytes_=1024,
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
        uploaded_by=new_user_id(),
    )
    await uow_factory.assets.add(asset)

    url = await use_case(tenant_id=tenant_id, asset_id=asset.id)

    assert url


async def test_requesting_a_download_for_an_unknown_asset_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), asset_id=new_asset_id())
