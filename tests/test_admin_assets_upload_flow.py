"""End-to-end HTTP test for the upload flow (D17, M3 Gate): an authenticated
admin session requests a presigned upload, then an unauthenticated PUT to
the token it received lands on ``webhooks.receive_upload``, gets verified,
and is registered as an ``Asset``. This is the path the Gate's "uploads are
verified server-side" bullet actually needs proven end-to-end, not just at
the use-case level (``test_verify_and_register_upload.py`` already covers
that in isolation).
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps.authorization import get_token_issuer
from app.api.deps.content_moderation import get_content_moderation_scanner
from app.api.deps.object_storage import get_object_storage
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.asset import AssetKind
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.content_moderation import FakeContentModerationScanner
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[
    object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec, InMemoryObjectStorage
]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    storage = InMemoryObjectStorage()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_content_moderation_scanner] = FakeContentModerationScanner
    return app, uow_factory, clock, codec, storage


def _bearer(
    codec: AccessTokenCodec, *, tenant_id: str, role: str, capabilities: list[str]
) -> dict[str, str]:
    token = codec.encode(
        AccessTokenClaims(
            subject=str(new_user_id()),
            tenant_id=tenant_id,
            role=role,
            capabilities=capabilities,
            is_platform_admin=False,
        ),
        now=utcnow(),
    )
    return {"Authorization": f"Bearer {token}"}


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 24), color="orange").save(buf, format="JPEG")
    return buf.getvalue()


async def test_a_requested_upload_is_verified_and_registered_end_to_end() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )
    data = _jpeg_bytes()

    async with await _client(app) as http:
        request_response = await http.post(
            "/api/v1/admin/assets/uploads",
            json={"kind": "input", "extension": "jpg", "content_type": "image/jpeg"},
            headers=headers,
        )
        assert request_response.status_code == 201
        upload = request_response.json()
        token = upload["url"].rsplit("/", 1)[-1]

        put_response = await http.put(
            f"/api/v1/webhooks/uploads/{token}",
            content=data,
            headers={"Content-Type": "image/jpeg"},
        )

    assert put_response.status_code == 204
    sha256 = hashlib.sha256(data).hexdigest()
    registered = await uow_factory.assets.get_by_sha256(tenant_id, sha256, AssetKind.INPUT)
    assert registered is not None
    assert registered.storage_key == upload["storage_key"]


async def test_an_uploaded_asset_can_be_downloaded_back_end_to_end() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )
    data = _jpeg_bytes()

    async with await _client(app) as http:
        request_response = await http.post(
            "/api/v1/admin/assets/uploads",
            json={"kind": "input", "extension": "jpg", "content_type": "image/jpeg"},
            headers=headers,
        )
        upload_token = request_response.json()["url"].rsplit("/", 1)[-1]
        await http.put(
            f"/api/v1/webhooks/uploads/{upload_token}",
            content=data,
            headers={"Content-Type": "image/jpeg"},
        )
        sha256 = hashlib.sha256(data).hexdigest()
        asset = await uow_factory.assets.get_by_sha256(tenant_id, sha256, AssetKind.INPUT)
        assert asset is not None

        download_request = await http.post(
            f"/api/v1/admin/assets/{asset.id}/download", headers=headers
        )
        assert download_request.status_code == 200
        download_token = download_request.json()["url"].rsplit("/", 1)[-1]

        download_response = await http.get(f"/api/v1/webhooks/uploads/{download_token}")

    assert download_response.status_code == 200
    assert download_response.content == data
    assert download_response.headers["content-type"] == "image/jpeg"


async def test_requesting_a_download_for_an_unknown_asset_is_not_found() -> None:
    app, _uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )

    async with await _client(app) as http:
        response = await http.post(f"/api/v1/admin/assets/{uuid.uuid4()}/download", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test_requesting_an_upload_requires_the_template_manage_capability() -> None:
    app, _uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/admin/assets/uploads",
            json={"kind": "input", "extension": "jpg", "content_type": "image/jpeg"},
            headers=headers,
        )

    assert response.status_code == 403


async def test_an_invalid_upload_token_is_rejected() -> None:
    app, _uow_factory, _clock, _codec, _storage = _build()

    async with await _client(app) as http:
        response = await http.put(
            "/api/v1/webhooks/uploads/not-a-real-token", content=_jpeg_bytes()
        )

    # Asserting the domain error code, not just the status - a bare 422 would
    # pass just as happily on FastAPI's own path-param validation, which
    # would prove nothing about `peek_upload` actually running.
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_an_upload_larger_than_its_declared_cap_is_rejected() -> None:
    app, _uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )

    async with await _client(app) as http:
        request_response = await http.post(
            "/api/v1/admin/assets/uploads",
            json={"kind": "input", "extension": "jpg", "content_type": "image/jpeg"},
            headers=headers,
        )
        token = request_response.json()["url"].rsplit("/", 1)[-1]

        put_response = await http.put(
            f"/api/v1/webhooks/uploads/{token}",
            content=b"x" * 25_000_000,
            headers={"Content-Type": "image/jpeg"},
        )

    assert put_response.status_code == 422
    assert put_response.json()["code"] == "validation_error"


async def test_requesting_a_generated_kind_upload_is_rejected() -> None:
    app, _uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/admin/assets/uploads",
            json={"kind": "generated", "extension": "jpg", "content_type": "image/jpeg"},
            headers=headers,
        )

    assert response.status_code == 422
