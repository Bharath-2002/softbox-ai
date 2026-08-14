from __future__ import annotations

import pytest

from app.entities.asset import Asset, AssetKind
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_tenant_id


def _kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "storage_key": "tenants/x/y.jpg",
        "sha256": "a" * 64,
        "mime": "image/jpeg",
        "width": 1080,
        "height": 1350,
        "bytes_": 204_800,
        "kind": AssetKind.INPUT,
        "source": "upload",
        "now": utcnow(),
    }
    base.update(overrides)
    return base


def test_a_new_asset_lower_cases_its_sha256() -> None:
    asset = Asset.create(new_tenant_id(), **_kwargs(sha256="A" * 64))

    assert asset.sha256 == "a" * 64
    assert asset.parent_asset_id is None
    assert asset.uploaded_by is None
    assert asset.meta == {}


def test_a_sha256_that_is_not_64_hex_characters_is_rejected() -> None:
    with pytest.raises(ValidationError, match="sha256"):
        Asset.create(new_tenant_id(), **_kwargs(sha256="not-a-hash"))


def test_a_non_positive_dimension_is_rejected() -> None:
    with pytest.raises(ValidationError, match="positive"):
        Asset.create(new_tenant_id(), **_kwargs(width=0))


def test_a_non_positive_byte_size_is_rejected() -> None:
    with pytest.raises(ValidationError, match="positive"):
        Asset.create(new_tenant_id(), **_kwargs(bytes_=0))
