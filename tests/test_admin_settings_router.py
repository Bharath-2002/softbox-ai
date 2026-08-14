"""HTTP-level tests for ``/api/v1/admin/settings/*`` (D16).

``test_the_admin_settings_router_has_no_platform_route`` pins the security
property the router's own module docstring claims: there is no path shape
this router exposes that could ever write a platform-wide default, because
``scope_type`` is never a request field at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.api.routers import admin_settings
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


async def test_upsert_and_resolve_a_tenant_setting_round_trip() -> None:
    app, _uow, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["settings.manage"]
    )

    async with await _client(app) as http:
        put_response = await http.put(
            "/api/v1/admin/settings/tenant/approval.required",
            json={"value": True},
            headers=headers,
        )
        assert put_response.status_code == 200

        get_response = await http.get("/api/v1/admin/settings/approval.required", headers=headers)

    assert get_response.status_code == 200
    assert get_response.json()["value"] is True


async def test_upsert_and_resolve_a_category_setting_overrides_the_tenant_one() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["settings.manage"]
    )

    async with await _client(app) as http:
        await http.put(
            "/api/v1/admin/settings/tenant/approval.required",
            json={"value": True},
            headers=headers,
        )
        await http.put(
            f"/api/v1/admin/settings/category/{category.id}/approval.required",
            json={"value": False},
            headers=headers,
        )

        resolved = await http.get(
            "/api/v1/admin/settings/approval.required",
            params={"category_id": str(category.id)},
            headers=headers,
        )

    assert resolved.json()["value"] is False


async def test_unset_key_resolves_to_a_null_value() -> None:
    app, _uow, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.get("/api/v1/admin/settings/qc.min_confidence", headers=headers)

    assert response.status_code == 200
    assert response.json()["value"] is None


async def test_writing_a_setting_requires_the_settings_manage_capability() -> None:
    app, _uow, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.put(
            "/api/v1/admin/settings/tenant/approval.required",
            json={"value": True},
            headers=headers,
        )

    assert response.status_code == 403


def test_the_admin_settings_router_has_no_platform_route() -> None:
    paths = {route.path for route in admin_settings.router.routes}  # type: ignore[attr-defined]
    assert not any("platform" in path for path in paths)
