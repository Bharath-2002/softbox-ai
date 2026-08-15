"""HTTP-level tests for ``/api/v1/admin/domains`` (D4, M8)."""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[object, FakeUnitOfWorkFactory, AccessTokenCodec]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: FakeClock(_NOW)
    app.dependency_overrides[get_token_issuer] = lambda: codec
    return app, uow_factory, codec


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


async def test_register_and_list_a_domain_round_trip() -> None:
    app, _uow, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["domains.manage"])

    async with await _client(app) as http:
        register_response = await http.post(
            "/api/v1/admin/domains", json={"hostname": "Shop.Example.COM"}, headers=headers
        )
        assert register_response.status_code == 201
        assert register_response.json()["hostname"] == "shop.example.com"
        assert register_response.json()["verified"] is False

        list_response = await http.get("/api/v1/admin/domains", headers=headers)

    assert list_response.status_code == 200
    hostnames = [row["hostname"] for row in list_response.json()]
    assert hostnames == ["shop.example.com"]


async def test_registering_a_domain_requires_the_domains_manage_capability() -> None:
    app, _uow, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/admin/domains", json={"hostname": "shop.example.com"}, headers=headers
        )

    assert response.status_code == 403


async def test_listing_domains_only_returns_the_callers_own_tenant() -> None:
    app, _uow, codec = _build()
    tenant_a = str(new_tenant_id())
    tenant_b = str(new_tenant_id())
    headers_a = _bearer(codec, tenant_id=tenant_a, role="admin", capabilities=["domains.manage"])
    headers_b = _bearer(codec, tenant_id=tenant_b, role="admin", capabilities=["domains.manage"])

    async with await _client(app) as http:
        await http.post(
            "/api/v1/admin/domains", json={"hostname": "a-shop.example.com"}, headers=headers_a
        )
        await http.post(
            "/api/v1/admin/domains", json={"hostname": "b-shop.example.com"}, headers=headers_b
        )

        list_a = await http.get("/api/v1/admin/domains", headers=headers_a)

    assert [row["hostname"] for row in list_a.json()] == ["a-shop.example.com"]
