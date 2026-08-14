"""HTTP-level tests for ``/api/v1/admin/.../templates*`` (D14) — the routes
that finally make M3's template work reachable from outside a test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.api.deps.object_storage import get_object_storage
from app.api.deps.vision_analysis import get_vision_analysis
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.asset import Asset, AssetKind
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory
from tests.fakes.vision_analysis import FakeVisionAnalysis

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
    app.dependency_overrides[get_vision_analysis] = FakeVisionAnalysis
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


async def _seed_slot(
    uow_factory: FakeUnitOfWorkFactory,
    tenant_id: TenantId,
    *,
    with_garment_body_requirement: bool = False,
) -> CatalogImageSlot:
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    slot = CatalogImageSlot.create(
        tenant_id,
        category.id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    await uow_factory.catalog_image_slots.add(slot)
    if with_garment_body_requirement:
        # Matches FakeVisionAnalysis's default `prompt_template`
        # ("A scene with {{input.garment_body}}."), so the analyse route's
        # D14a validation passes and reaches `analysed`, not `invalid`.
        garment_body = InputImageSlot.create(
            tenant_id, category.id, key="garment_body", label="Garment body", now=_NOW
        )
        await uow_factory.input_image_slots.add(garment_body)
        requirement = CatalogSlotInputRequirement.create(
            tenant_id, slot.id, garment_body.id, role="garment_body", prompt_position=0, now=_NOW
        )
        await uow_factory.catalog_slot_input_requirements.add(requirement)
    return slot


async def test_creating_an_authored_template_reaches_analysed_over_http() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    slot = await _seed_slot(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/catalog-image-slots/{slot.id}/templates/authored",
            json={"name": "Marble tabletop", "prompt_template": "A plain scene, no placeholders."},
            headers=headers,
        )

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "authored_scene"
    assert body["status"] == "analysed"


async def test_creating_an_authored_template_requires_template_manage() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    slot = await _seed_slot(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/catalog-image-slots/{slot.id}/templates/authored",
            json={"name": "Marble tabletop", "prompt_template": "x"},
            headers=headers,
        )

    assert response.status_code == 403


async def test_the_full_upload_then_analyse_then_archive_flow() -> None:
    app, uow_factory, clock, codec, storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    slot = await _seed_slot(uow_factory, tenant_id, with_garment_body_requirement=True)
    asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/template/a.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=AssetKind.TEMPLATE,
        source="upload",
        now=clock.now(),
    )
    await uow_factory.assets.add(asset)
    await storage.write(asset.storage_key, b"fake-image-bytes")
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["template.manage"]
    )

    async with await _client(app) as http:
        create_response = await http.post(
            f"/api/v1/admin/catalog-image-slots/{slot.id}/templates/from-upload",
            json={"name": "Studio flatlay", "source_asset_id": str(asset.id)},
            headers=headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["status"] == "uploaded"
        template_id = create_response.json()["id"]

        list_response = await http.get(
            f"/api/v1/admin/catalog-image-slots/{slot.id}/templates", headers=headers
        )
        assert [t["id"] for t in list_response.json()] == [template_id]

        analyse_response = await http.post(
            f"/api/v1/admin/templates/{template_id}/analyse", headers=headers
        )
        assert analyse_response.status_code == 200
        assert analyse_response.json()["status"] == "analysed"

        archive_response = await http.post(
            f"/api/v1/admin/templates/{template_id}/archive", headers=headers
        )

    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"
