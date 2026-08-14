from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.asset import AssetKind
from app.features.assets.request_upload import RequestUpload
from app.shared.errors import ValidationError
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage


def _use_case() -> RequestUpload:
    return RequestUpload(InMemoryObjectStorage(), FakeClock(datetime(2026, 1, 1, tzinfo=UTC)))


async def test_requesting_an_upload_returns_a_presigned_put() -> None:
    use_case = _use_case()

    upload = await use_case(
        tenant_id=new_tenant_id(),
        kind=AssetKind.INPUT,
        extension="jpg",
        content_type="image/jpeg",
        uploaded_by=new_user_id(),
    )

    assert upload.method == "PUT"
    assert upload.storage_key
    assert upload.url


async def test_generated_kind_cannot_be_requested_for_upload() -> None:
    use_case = _use_case()

    with pytest.raises(ValidationError, match="cannot be uploaded directly"):
        await use_case(
            tenant_id=new_tenant_id(),
            kind=AssetKind.GENERATED,
            extension="jpg",
            content_type="image/jpeg",
            uploaded_by=new_user_id(),
        )
