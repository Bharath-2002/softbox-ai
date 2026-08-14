from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest
from PIL import Image

from app.entities.asset import AssetKind
from app.features.assets.verify_and_register_upload import VerifyAndRegisterUpload
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.content_moderation import FakeContentModerationScanner
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _jpeg_bytes(*, width: int = 40, height: int = 30) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color="green").save(buf, format="JPEG")
    return buf.getvalue()


def _use_case(
    **overrides: object,
) -> tuple[
    VerifyAndRegisterUpload,
    InMemoryObjectStorage,
    FakeContentModerationScanner,
    FakeUnitOfWorkFactory,
]:
    storage = InMemoryObjectStorage()
    scanner = FakeContentModerationScanner()
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    use_case = VerifyAndRegisterUpload(uow_factory, storage, scanner, clock, **overrides)
    return use_case, storage, scanner, uow_factory


async def test_a_valid_upload_is_registered_as_an_asset() -> None:
    use_case, storage, _scanner, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    uploader = new_user_id()
    key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(key, _jpeg_bytes(width=64, height=48))

    asset = await use_case(
        tenant_id=tenant_id, storage_key=key, kind=AssetKind.INPUT, uploaded_by=uploader
    )

    assert asset.mime == "image/jpeg"
    assert asset.width == 64
    assert asset.height == 48
    assert asset.uploaded_by == uploader
    stored = await uow_factory.assets.get(tenant_id, asset.id)
    assert stored is not None


async def test_an_oversized_upload_is_rejected_and_deleted_from_storage() -> None:
    use_case, storage, _scanner, _uow_factory = _use_case(max_bytes=10)
    tenant_id = new_tenant_id()
    key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(key, _jpeg_bytes())

    with pytest.raises(ValidationError, match="maximum allowed size"):
        await use_case(
            tenant_id=tenant_id, storage_key=key, kind=AssetKind.INPUT, uploaded_by=new_user_id()
        )

    with pytest.raises(NotFoundError):
        await storage.read(key)


async def test_a_file_that_is_not_really_an_image_is_rejected() -> None:
    use_case, storage, _scanner, _uow_factory = _use_case()
    tenant_id = new_tenant_id()
    key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(key, b"not-an-image-at-all")

    with pytest.raises(ValidationError, match="not a readable image"):
        await use_case(
            tenant_id=tenant_id, storage_key=key, kind=AssetKind.INPUT, uploaded_by=new_user_id()
        )


async def test_an_oversized_dimension_is_rejected() -> None:
    use_case, storage, _scanner, _uow_factory = _use_case(max_dimension=50)
    tenant_id = new_tenant_id()
    key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(key, _jpeg_bytes(width=100, height=100))

    with pytest.raises(ValidationError, match="dimensions exceed"):
        await use_case(
            tenant_id=tenant_id, storage_key=key, kind=AssetKind.INPUT, uploaded_by=new_user_id()
        )


async def test_content_flagged_unsafe_by_moderation_is_rejected() -> None:
    use_case, storage, scanner, _uow_factory = _use_case()
    scanner.reject_reason = "flagged"
    tenant_id = new_tenant_id()
    key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(key, _jpeg_bytes())

    with pytest.raises(ValidationError, match="flagged"):
        await use_case(
            tenant_id=tenant_id, storage_key=key, kind=AssetKind.INPUT, uploaded_by=new_user_id()
        )


async def test_a_second_upload_of_identical_bytes_dedups_to_the_first_asset() -> None:
    use_case, storage, _scanner, _uow_factory = _use_case()
    tenant_id = new_tenant_id()
    uploader = new_user_id()
    data = _jpeg_bytes()
    first_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    second_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(first_key, data)
    await storage.write(second_key, data)

    first_asset = await use_case(
        tenant_id=tenant_id, storage_key=first_key, kind=AssetKind.INPUT, uploaded_by=uploader
    )
    second_asset = await use_case(
        tenant_id=tenant_id, storage_key=second_key, kind=AssetKind.INPUT, uploaded_by=uploader
    )

    assert second_asset.id == first_asset.id
    with pytest.raises(NotFoundError):
        await storage.read(second_key)


async def test_generated_kind_cannot_be_uploaded_directly() -> None:
    use_case, storage, _scanner, _uow_factory = _use_case()
    tenant_id = new_tenant_id()
    key = storage.new_storage_key(tenant_id, kind="generated", extension="jpg")
    await storage.write(key, _jpeg_bytes())

    with pytest.raises(ValidationError, match="cannot be uploaded directly"):
        await use_case(
            tenant_id=tenant_id,
            storage_key=key,
            kind=AssetKind.GENERATED,
            uploaded_by=new_user_id(),
        )
