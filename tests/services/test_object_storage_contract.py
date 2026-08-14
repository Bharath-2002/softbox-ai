"""Runs against both InMemoryObjectStorage and LocalObjectStorage. Unlike
the repository contracts, neither side needs Postgres, so there is no
``fake``/``real`` split gated by ``TEST_DATABASE_URL`` — both are exercised
in every run.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio

from app.infrastructure.storage.local_object_storage import LocalObjectStorage, PresignTokenCodec
from app.services.ports.object_storage import ObjectStorage
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.object_storage import InMemoryObjectStorage

_SIGNING_KEY = "a-sufficiently-long-object-storage-signing-secret"


@dataclass
class Context:
    storage: ObjectStorage


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest, tmp_path: object) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(InMemoryObjectStorage())
        return

    storage = LocalObjectStorage(
        root=str(tmp_path), base_url="http://test", signing_key=_SIGNING_KEY
    )
    yield Context(storage)


async def test_reading_an_unwritten_key_is_not_found(ctx: Context) -> None:
    key = ctx.storage.new_storage_key(new_tenant_id(), kind="input", extension="jpg")

    with pytest.raises(NotFoundError):
        await ctx.storage.read(key)


async def test_write_then_read_round_trips(ctx: Context) -> None:
    key = ctx.storage.new_storage_key(new_tenant_id(), kind="input", extension="jpg")

    await ctx.storage.write(key, b"raw-bytes")

    assert await ctx.storage.read(key) == b"raw-bytes"


async def test_delete_then_read_is_not_found(ctx: Context) -> None:
    key = ctx.storage.new_storage_key(new_tenant_id(), kind="input", extension="jpg")
    await ctx.storage.write(key, b"raw-bytes")

    await ctx.storage.delete(key)

    with pytest.raises(NotFoundError):
        await ctx.storage.read(key)


async def test_deleting_an_unwritten_key_does_not_raise(ctx: Context) -> None:
    key = ctx.storage.new_storage_key(new_tenant_id(), kind="input", extension="jpg")

    await ctx.storage.delete(key)


async def test_presign_put_returns_the_same_storage_key(ctx: Context) -> None:
    tenant_id = new_tenant_id()
    key = ctx.storage.new_storage_key(tenant_id, kind="template", extension="png")

    upload = await ctx.storage.presign_put(
        tenant_id=tenant_id,
        storage_key=key,
        kind="template",
        uploaded_by=new_user_id(),
        content_type="image/png",
        max_bytes=10_000_000,
        now=utcnow(),
        expires_in=timedelta(minutes=10),
    )

    assert upload.storage_key == key
    assert upload.method == "PUT"


async def test_accept_upload_writes_bytes_and_returns_the_sealed_claims(ctx: Context) -> None:
    tenant_id = new_tenant_id()
    uploader = new_user_id()
    key = ctx.storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    now = utcnow()
    upload = await ctx.storage.presign_put(
        tenant_id=tenant_id,
        storage_key=key,
        kind="input",
        uploaded_by=uploader,
        content_type="image/jpeg",
        max_bytes=1_000,
        now=now,
        expires_in=timedelta(minutes=10),
    )
    token = upload.url.rsplit("/", 1)[-1]

    claims = await ctx.storage.accept_upload(token, b"raw-bytes", now=now)

    assert claims.tenant_id == tenant_id
    assert claims.storage_key == key
    assert claims.kind == "input"
    assert claims.uploaded_by == uploader
    assert await ctx.storage.read(key) == b"raw-bytes"


async def test_peek_upload_returns_claims_and_cap_without_writing_anything(ctx: Context) -> None:
    tenant_id = new_tenant_id()
    uploader = new_user_id()
    key = ctx.storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    now = utcnow()
    upload = await ctx.storage.presign_put(
        tenant_id=tenant_id,
        storage_key=key,
        kind="input",
        uploaded_by=uploader,
        content_type="image/jpeg",
        max_bytes=1_234,
        now=now,
        expires_in=timedelta(minutes=10),
    )
    token = upload.url.rsplit("/", 1)[-1]

    claims, max_bytes = await ctx.storage.peek_upload(token, now=now)

    assert claims.tenant_id == tenant_id
    assert claims.storage_key == key
    assert max_bytes == 1_234
    with pytest.raises(NotFoundError):
        await ctx.storage.read(key)


async def test_accept_upload_rejects_bytes_over_the_declared_cap(ctx: Context) -> None:
    tenant_id = new_tenant_id()
    key = ctx.storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    now = utcnow()
    upload = await ctx.storage.presign_put(
        tenant_id=tenant_id,
        storage_key=key,
        kind="input",
        uploaded_by=new_user_id(),
        content_type="image/jpeg",
        max_bytes=4,
        now=now,
        expires_in=timedelta(minutes=10),
    )
    token = upload.url.rsplit("/", 1)[-1]

    with pytest.raises(ValidationError):
        await ctx.storage.accept_upload(token, b"way-too-many-bytes", now=now)


async def test_resolve_download_reads_back_what_was_written(ctx: Context) -> None:
    tenant_id = new_tenant_id()
    key = ctx.storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await ctx.storage.write(key, b"secret-bytes")
    now = utcnow()

    download_url = await ctx.storage.presign_get(
        key, content_type="image/jpeg", now=now, expires_in=timedelta(minutes=10)
    )
    token = download_url.rsplit("/", 1)[-1]

    downloaded = await ctx.storage.resolve_download(token, now=now)
    assert downloaded.data == b"secret-bytes"
    assert downloaded.content_type == "image/jpeg"


async def test_new_storage_key_is_namespaced_by_tenant(ctx: Context) -> None:
    tenant_id = new_tenant_id()

    key = ctx.storage.new_storage_key(tenant_id, kind="input", extension="jpg")

    assert str(tenant_id) in key


def test_presign_token_round_trips_through_the_codec() -> None:
    codec = PresignTokenCodec(_SIGNING_KEY)
    now = utcnow()

    token = codec.encode(
        storage_key="tenants/x/input/a.jpg",
        purpose="put",
        now=now,
        expires_in=timedelta(minutes=10),
        content_type="image/jpeg",
        max_bytes=1_000_000,
    )
    claims = codec.decode(token, purpose="put", now=now)

    assert claims["storage_key"] == "tenants/x/input/a.jpg"
    assert claims["content_type"] == "image/jpeg"
    assert claims["max_bytes"] == 1_000_000


def test_presign_token_rejects_the_wrong_purpose() -> None:
    codec = PresignTokenCodec(_SIGNING_KEY)
    now = utcnow()
    token = codec.encode(
        storage_key="tenants/x/input/a.jpg",
        purpose="put",
        now=now,
        expires_in=timedelta(minutes=10),
    )

    with pytest.raises(ValidationError):
        codec.decode(token, purpose="get", now=now)


def test_presign_token_rejects_after_expiry() -> None:
    codec = PresignTokenCodec(_SIGNING_KEY)
    now = utcnow()
    token = codec.encode(
        storage_key="tenants/x/input/a.jpg",
        purpose="get",
        now=now,
        expires_in=timedelta(minutes=10),
    )

    with pytest.raises(ValidationError):
        codec.decode(token, purpose="get", now=now + timedelta(minutes=11))


def test_a_short_signing_key_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="32 characters"):
        PresignTokenCodec("too-short")


async def test_local_storage_rejects_a_storage_key_that_escapes_the_root(
    tmp_path: object,
) -> None:
    storage = LocalObjectStorage(
        root=str(tmp_path), base_url="http://test", signing_key=_SIGNING_KEY
    )

    with pytest.raises(ValidationError):
        await storage.read("../outside.txt")
