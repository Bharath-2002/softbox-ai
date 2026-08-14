"""HTTP-level tests for input/catalog image slots and the sharing join
(D13) — chunk C of the M2 Admin API.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.category import Category
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    return app, uow_factory, clock, codec


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


async def _seed_category(uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId) -> Category:
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    return category


async def test_full_slot_and_requirement_lifecycle_over_http() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        input_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/input-image-slots",
            json={"key": "border_detail", "label": "Border"},
            headers=headers,
        )
        assert input_response.status_code == 201
        input_slot_id = input_response.json()["id"]

        catalog_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/catalog-image-slots",
            json={
                "key": "closeup",
                "label": "Close-up",
                "aspect_ratio": "4:5",
                "target_width": 1080,
                "target_height": 1350,
            },
            headers=headers,
        )
        assert catalog_response.status_code == 201
        catalog_slot_id = catalog_response.json()["id"]

        attach_response = await http.post(
            f"/api/v1/admin/catalog-image-slots/{catalog_slot_id}/requirements",
            json={
                "input_image_slot_id": input_slot_id,
                "role": "garment_body",
                "prompt_position": 0,
            },
            headers=headers,
        )
        assert attach_response.status_code == 201

        list_response = await http.get(
            f"/api/v1/admin/catalog-image-slots/{catalog_slot_id}/requirements", headers=headers
        )
        assert [r["role"] for r in list_response.json()] == ["garment_body"]

        update_response = await http.patch(
            f"/api/v1/admin/catalog-image-slots/{catalog_slot_id}/requirements/{input_slot_id}",
            json={"role": "border_detail", "prompt_position": 1},
            headers=headers,
        )
        assert update_response.status_code == 200
        assert update_response.json()["role"] == "border_detail"

        detach_response = await http.delete(
            f"/api/v1/admin/catalog-image-slots/{catalog_slot_id}/requirements/{input_slot_id}",
            headers=headers,
        )
        assert detach_response.status_code == 204

        after_detach = await http.get(
            f"/api/v1/admin/catalog-image-slots/{catalog_slot_id}/requirements", headers=headers
        )

    assert after_detach.json() == []


async def test_creating_a_slot_requires_the_taxonomy_capability() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/categories/{category.id}/input-image-slots",
            json={"key": "border_detail", "label": "Border"},
            headers=headers,
        )

    assert response.status_code == 403
