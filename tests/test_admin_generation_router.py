"""HTTP-level test for ``POST /api/v1/admin/generation/render-next`` (D18,
D19) — the M5 render step's admin trigger, the same known-interim shape
``POST .../templates/{id}/analyse`` already uses.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps.authorization import get_token_issuer
from app.api.deps.image_generation import get_image_generation
from app.api.deps.object_storage import get_object_storage
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.features.generation.start_generation_item_render import JOB_TYPE
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.image_generation import GeneratedImage
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import (
    TenantId,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_category_spec_version_id,
    new_product_id,
    new_product_variant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.image_generation import FakeImageGeneration
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[
    object,
    FakeUnitOfWorkFactory,
    FakeClock,
    AccessTokenCodec,
    InMemoryObjectStorage,
    FakeImageGeneration,
]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    storage = InMemoryObjectStorage()
    image_generation = FakeImageGeneration()
    image_generation.next_result = GeneratedImage(
        image_bytes=_png_bytes(), mime="image/png", cost_micros=2_000, latency_ms=500
    )
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_image_generation] = lambda: image_generation
    return app, uow_factory, clock, codec, storage, image_generation


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), color="blue").save(buf, format="PNG")
    return buf.getvalue()


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


async def _seed(uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId) -> None:
    request = GenerationRequest.create(
        tenant_id,
        new_product_id(),
        new_product_variant_id(),
        new_category_spec_version_id(),
        settings_snapshot={},
        quota_reservation_id=None,
        requested_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.generation_requests.add(request)

    item = GenerationItem.create(
        tenant_id,
        request.id,
        new_catalog_image_slot_id(),
        new_catalog_template_id(),
        attempt_no=1,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={},
        seed=1,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=[],
        now=_NOW,
    )
    await uow_factory.generation_items.add(item)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"generation_item_id": str(item.id)},
        run_at=_NOW,
        now=_NOW,
    )


async def test_render_next_over_http_renders_a_claimable_item() -> None:
    app, uow_factory, _clock, codec, _storage, _image_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    await _seed(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/generation/render-next", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["status"] == "succeeded"


async def test_render_next_over_http_returns_null_when_nothing_is_claimable() -> None:
    app, _uow_factory, _clock, codec, _storage, _image_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/generation/render-next", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_render_next_requires_the_product_manage_capability() -> None:
    app, _uow_factory, _clock, codec, _storage, _image_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/generation/render-next", headers=headers)

    assert response.status_code == 403
